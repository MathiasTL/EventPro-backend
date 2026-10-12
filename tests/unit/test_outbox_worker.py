"""Prueba de humo del worker de arq: WorkerSettings se importa y registra el cron."""

from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from arq.worker import create_worker
from structlog.testing import capture_logs

from app.application.use_cases.messaging.dispatch_due_messages import (
    DispatchDueMessages,
    DispatchSummary,
)
from app.core.config import Settings, get_settings
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.di import containers

_MODULE = "app.infrastructure.adapters.primary.jobs.worker"
_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def _reset() -> None:
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    containers.clear_application_caches()
    sys.modules.pop(_MODULE, None)


@pytest.fixture
def worker(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    monkeypatch.setenv("REDIS_HOST", "redis-de-prueba")
    _reset()
    yield importlib.import_module(_MODULE)
    _reset()


class _RecordingUseCase:
    def __init__(self, summary: DispatchSummary | None = None) -> None:
        self.summary = summary or DispatchSummary()
        self.calls = 0
        self.gate: asyncio.Event | None = None
        self.error: Exception | None = None

    async def execute(self) -> DispatchSummary:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return self.summary


def _ctx(use_case: _RecordingUseCase) -> dict[str, Any]:
    return {"dispatch_lock": asyncio.Lock(), "dispatch_due_messages": use_case}


def test_worker_settings_registers_the_dispatch_cron_every_five_seconds(
    worker: ModuleType,
) -> None:
    (job,) = worker.WorkerSettings.cron_jobs

    assert job.name == "dispatch_outbox"
    assert job.coroutine is worker.dispatch_outbox
    assert job.second == set(range(0, 60, 5))
    assert job.unique is True
    assert job.max_tries == 1
    assert job.timeout_s == worker.CYCLE_TIMEOUT_SECONDS
    assert job.minute is None and job.hour is None


def test_cycle_timeout_is_shorter_than_the_default_lease(worker: ModuleType) -> None:
    assert Settings.model_fields["outbox_lease_seconds"].default > worker.CYCLE_TIMEOUT_SECONDS


def test_worker_settings_use_the_configured_redis_and_lifecycle_hooks(
    worker: ModuleType,
) -> None:
    settings = worker.WorkerSettings
    assert settings.redis_settings.host == "redis-de-prueba"
    assert settings.on_startup is worker.startup
    assert settings.on_shutdown is worker.shutdown


async def test_arq_can_build_a_worker_from_the_settings(worker: ModuleType) -> None:
    arq_worker = create_worker(worker.WorkerSettings)
    try:
        assert [job.name for job in arq_worker.cron_jobs] == ["dispatch_outbox"]
    finally:
        await arq_worker.close()


def test_docker_compose_starts_the_worker_with_these_settings(worker: ModuleType) -> None:
    assert f'["arq", "{_MODULE}.WorkerSettings"]' in _COMPOSE.read_text(encoding="utf-8")
    assert importlib.import_module(_MODULE).WorkerSettings is worker.WorkerSettings


async def test_dispatch_outbox_runs_one_cycle_and_returns_the_summary(
    worker: ModuleType,
) -> None:
    use_case = _RecordingUseCase(DispatchSummary(claimed=3, sent=2, rescheduled=1))

    with capture_logs() as logs:
        result = await worker.dispatch_outbox(_ctx(use_case))

    assert use_case.calls == 1
    assert result == {
        "claimed": 3,
        "sent": 2,
        "rescheduled": 1,
        "failed": 0,
        "discarded": 0,
        "errors": 0,
    }
    assert [entry["event"] for entry in logs] == ["outbox_cycle_done"]


async def test_an_idle_cycle_does_not_log(worker: ModuleType) -> None:
    with capture_logs() as logs:
        await worker.dispatch_outbox(_ctx(_RecordingUseCase()))
    assert logs == []


async def test_a_slow_cycle_is_not_overlapped_by_the_next_tick(worker: ModuleType) -> None:
    use_case = _RecordingUseCase()
    use_case.gate = asyncio.Event()
    ctx = _ctx(use_case)

    running = asyncio.create_task(worker.dispatch_outbox(ctx))
    await asyncio.sleep(0)
    with capture_logs() as logs:
        skipped = await worker.dispatch_outbox(ctx)
    use_case.gate.set()
    await running

    assert skipped is None
    assert use_case.calls == 1
    assert [entry["event"] for entry in logs] == ["outbox_cycle_skipped_overlap"]


async def test_a_failing_cycle_propagates_and_releases_the_lock(worker: ModuleType) -> None:
    use_case = _RecordingUseCase()
    use_case.error = ConnectionError("base de datos caída")
    ctx = _ctx(use_case)

    with pytest.raises(ConnectionError):
        await worker.dispatch_outbox(ctx)

    use_case.error = None
    await worker.dispatch_outbox(ctx)  # el ciclo siguiente se ejecuta con normalidad
    assert use_case.calls == 2


async def test_startup_wires_the_use_case_and_warns_about_the_fake_gateway(
    worker: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    # configure_logging reconfigura structlog y desactivaría la captura de la prueba.
    monkeypatch.setattr(worker, "configure_logging", lambda level: None)
    ctx: dict[str, Any] = {}

    with capture_logs() as logs:
        await worker.startup(ctx)
    try:
        assert isinstance(ctx["dispatch_due_messages"], DispatchDueMessages)
        assert isinstance(ctx["dispatch_lock"], asyncio.Lock)
        assert [entry["event"] for entry in logs] == ["worker_using_fake_messaging"]
    finally:
        await worker.shutdown(ctx)
