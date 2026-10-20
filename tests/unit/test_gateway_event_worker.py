"""Trabajo de arq ``process_gateway_event``: registro, reintentos acotados y cierre del worker."""

from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

import pytest
from arq import Retry
from arq.worker import create_worker
from structlog.testing import capture_logs

from app.application.dtos.gateway_event_dto import GatewayEventOutcome
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.core.config import get_settings
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.queue.arq_gateway_event_queue import (
    GATEWAY_EVENT_DEFER_SECONDS,
    PROCESS_GATEWAY_EVENT_JOB,
)
from app.infrastructure.di import containers

_MODULE = "app.infrastructure.adapters.primary.jobs.worker"
RAW_BODY = b'{"event": "message_updated", "content": "Codigo 123456"}'
RECEIVED_AT_EPOCH = 1_791_813_660


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
    def __init__(
        self,
        outcome: GatewayEventOutcome = GatewayEventOutcome.APPLIED,
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self, *, raw_body: bytes, received_at: datetime, last_attempt: bool = False
    ) -> GatewayEventOutcome:
        self.calls.append(
            {"raw_body": raw_body, "received_at": received_at, "last_attempt": last_attempt}
        )
        if self.error is not None:
            raise self.error
        return self.outcome


def _ctx(use_case: _RecordingUseCase, job_try: int | None = 1) -> dict[str, Any]:
    ctx: dict[str, Any] = {"process_gateway_event": use_case}
    if job_try is not None:
        ctx["job_try"] = job_try
    return ctx


# --- Registro -----------------------------------------------------------------------------


def test_the_job_is_registered_with_bounded_tries_and_no_kept_result(worker: ModuleType) -> None:
    (job,) = worker.WorkerSettings.functions

    assert job.name == PROCESS_GATEWAY_EVENT_JOB == "process_gateway_event"
    assert job.coroutine is worker.process_gateway_event
    assert job.max_tries == worker.GATEWAY_EVENT_MAX_TRIES == 5
    assert job.keep_result_s == 0
    assert job.timeout_s == 30


def test_the_dispatch_cron_keeps_working_next_to_the_new_job(worker: ModuleType) -> None:
    assert [cron.name for cron in worker.WorkerSettings.cron_jobs] == ["dispatch_outbox"]


def test_events_are_enqueued_with_a_short_defer_so_sent_is_committed_first() -> None:
    assert GATEWAY_EVENT_DEFER_SECONDS == 2


async def test_arq_can_build_a_worker_that_knows_the_job(worker: ModuleType) -> None:
    arq_worker = create_worker(worker.WorkerSettings)
    try:
        assert PROCESS_GATEWAY_EVENT_JOB in arq_worker.functions
    finally:
        await arq_worker.close()


# --- Resultados que terminan el trabajo ---------------------------------------------------


@pytest.mark.parametrize(
    "outcome",
    [
        GatewayEventOutcome.APPLIED,
        GatewayEventOutcome.IGNORED,
        GatewayEventOutcome.UNRESOLVED,
        GatewayEventOutcome.UNHANDLED,
        GatewayEventOutcome.MALFORMED,
    ],
)
async def test_final_outcomes_return_normally_without_retry(
    worker: ModuleType, outcome: GatewayEventOutcome
) -> None:
    use_case = _RecordingUseCase(outcome)

    result = await worker.process_gateway_event(_ctx(use_case), RAW_BODY, RECEIVED_AT_EPOCH)

    assert result == outcome.value
    assert len(use_case.calls) == 1


async def test_the_receive_time_is_passed_as_an_aware_utc_datetime(worker: ModuleType) -> None:
    use_case = _RecordingUseCase()

    await worker.process_gateway_event(_ctx(use_case), RAW_BODY, RECEIVED_AT_EPOCH)

    (call,) = use_case.calls
    assert call["raw_body"] == RAW_BODY
    assert call["received_at"] == datetime.fromtimestamp(RECEIVED_AT_EPOCH, UTC)
    assert call["received_at"].tzinfo is UTC


async def test_the_job_try_defaults_to_the_first_attempt(worker: ModuleType) -> None:
    use_case = _RecordingUseCase(GatewayEventOutcome.UNKNOWN_MESSAGE)

    with pytest.raises(Retry) as retry:
        await worker.process_gateway_event(_ctx(use_case, job_try=None), RAW_BODY, 1)

    assert retry.value.defer_score == 5_000
    assert use_case.calls[0]["last_attempt"] is False


# --- Mensaje desconocido: reintento con espera creciente ----------------------------------


@pytest.mark.parametrize(("job_try", "defer_seconds"), [(1, 5), (2, 10), (3, 20), (4, 40)])
async def test_an_unknown_message_is_retried_with_a_growing_defer(
    worker: ModuleType, job_try: int, defer_seconds: int
) -> None:
    use_case = _RecordingUseCase(GatewayEventOutcome.UNKNOWN_MESSAGE)

    with pytest.raises(Retry) as retry:
        await worker.process_gateway_event(_ctx(use_case, job_try), RAW_BODY, RECEIVED_AT_EPOCH)

    assert retry.value.defer_score == defer_seconds * 1000
    assert use_case.calls[0]["last_attempt"] is False


async def test_the_last_try_of_an_unknown_message_ends_without_raising(
    worker: ModuleType,
) -> None:
    use_case = _RecordingUseCase(GatewayEventOutcome.UNKNOWN_MESSAGE)

    result = await worker.process_gateway_event(
        _ctx(use_case, worker.GATEWAY_EVENT_MAX_TRIES), RAW_BODY, RECEIVED_AT_EPOCH
    )

    assert result == "UNKNOWN_MESSAGE"
    assert use_case.calls[0]["last_attempt"] is True


# --- Gateway caído: reintento y cierre ----------------------------------------------------


@pytest.mark.parametrize(("job_try", "defer_seconds"), [(1, 5), (2, 10), (4, 40)])
async def test_an_unavailable_gateway_is_retried_with_the_same_defer(
    worker: ModuleType, job_try: int, defer_seconds: int
) -> None:
    use_case = _RecordingUseCase(error=MessagingUnavailableError("Chatwoot respondió 503"))

    with pytest.raises(Retry) as retry:
        await worker.process_gateway_event(_ctx(use_case, job_try), RAW_BODY, RECEIVED_AT_EPOCH)

    assert retry.value.defer_score == defer_seconds * 1000
    assert use_case.calls[0]["last_attempt"] is False


async def test_the_last_try_of_an_unavailable_gateway_is_logged_and_returns(
    worker: ModuleType,
) -> None:
    use_case = _RecordingUseCase(error=MessagingUnavailableError("Chatwoot respondió 503"))

    with capture_logs() as logs:
        result = await worker.process_gateway_event(
            _ctx(use_case, worker.GATEWAY_EVENT_MAX_TRIES), RAW_BODY, RECEIVED_AT_EPOCH
        )

    assert result == "GATEWAY_UNAVAILABLE"
    assert [entry["event"] for entry in logs] == ["delivery_notice_lookup_failed"]
    assert logs[0]["job_try"] == worker.GATEWAY_EVENT_MAX_TRIES
    assert use_case.calls[0]["last_attempt"] is True


async def test_an_unexpected_error_propagates_to_arq(worker: ModuleType) -> None:
    use_case = _RecordingUseCase(error=RuntimeError("base de datos caída"))

    with pytest.raises(RuntimeError, match="base de datos caída"):
        await worker.process_gateway_event(_ctx(use_case), RAW_BODY, RECEIVED_AT_EPOCH)


async def test_the_job_never_logs_the_body(worker: ModuleType) -> None:
    unknown = _RecordingUseCase(GatewayEventOutcome.UNKNOWN_MESSAGE)
    down = _RecordingUseCase(error=MessagingUnavailableError("Chatwoot respondió 503"))

    with capture_logs() as logs:
        for use_case in (unknown, down):
            await worker.process_gateway_event(
                _ctx(use_case, worker.GATEWAY_EVENT_MAX_TRIES), RAW_BODY, RECEIVED_AT_EPOCH
            )

    assert logs
    assert "123456" not in repr(logs)


# --- Ciclo de vida ------------------------------------------------------------------------


async def test_startup_wires_the_gateway_event_use_case(
    worker: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "configure_logging", lambda level: None)
    ctx: dict[str, Any] = {}

    await worker.startup(ctx)
    try:
        assert isinstance(ctx["process_gateway_event"], ProcessGatewayEvent)
        assert isinstance(ctx["dispatch_lock"], asyncio.Lock)
    finally:
        await worker.shutdown(ctx)


async def test_shutdown_releases_all_infrastructure(
    worker: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def fake_shutdown() -> None:
        calls.append("shutdown_infrastructure")

    monkeypatch.setattr(worker, "shutdown_infrastructure", fake_shutdown)

    await worker.shutdown({})

    assert calls == ["shutdown_infrastructure"]
