"""ArqGatewayEventQueue: argumentos exactos del trabajo, identificador y espera inicial."""

import importlib
import inspect
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from types import ModuleType
from typing import Any

import pytest

from app.core.config import get_settings
from app.infrastructure.adapters.secondary.persistence.database import (
    get_engine,
    get_sessionmaker,
)
from app.infrastructure.adapters.secondary.queue.arq_gateway_event_queue import (
    GATEWAY_EVENT_DEFER_SECONDS,
    PROCESS_GATEWAY_EVENT_JOB,
    ArqGatewayEventQueue,
)
from app.infrastructure.di import containers

_WORKER = "app.infrastructure.adapters.primary.jobs.worker"
RECEIVED_AT = datetime(2026, 10, 12, 14, 1, 0, tzinfo=UTC)
RECEIVED_AT_EPOCH = 1_791_813_660
BODY = b'{"event": "message_updated", "content": "Codigo 123456"}'


class FakePool:
    """Doble de ``ArqRedis`` que solo registra las llamadas a ``enqueue_job``."""

    def __init__(self, *, error: Exception | None = None, result: object = object()) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._error = error
        self._result = result

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> object:
        self.calls.append((args, kwargs))
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def worker(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    monkeypatch.setenv("REDIS_HOST", "redis-de-prueba")
    _reset()
    yield importlib.import_module(_WORKER)
    _reset()


def _reset() -> None:
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    containers.clear_application_caches()
    sys.modules.pop(_WORKER, None)


async def test_the_job_is_enqueued_with_name_body_epoch_id_and_a_non_zero_defer() -> None:
    pool = FakePool()

    await ArqGatewayEventQueue(pool).enqueue(  # type: ignore[arg-type]
        event_id="0b9f-uuid", raw_body=BODY, received_at=RECEIVED_AT
    )

    assert pool.calls == [
        (
            (PROCESS_GATEWAY_EVENT_JOB, BODY, RECEIVED_AT_EPOCH),
            {"_job_id": "chatwoot:0b9f-uuid", "_defer_by": GATEWAY_EVENT_DEFER_SECONDS},
        )
    ]
    assert GATEWAY_EVENT_DEFER_SECONDS == 2


async def test_the_body_is_passed_as_the_exact_bytes() -> None:
    pool = FakePool()
    pretty = b'{\n  "event": "message_updated"\n}'

    await ArqGatewayEventQueue(pool).enqueue(  # type: ignore[arg-type]
        event_id="A", raw_body=pretty, received_at=RECEIVED_AT
    )

    assert pool.calls[0][0][1] is pretty


async def test_the_epoch_is_the_instant_even_when_the_zone_is_not_utc() -> None:
    pool = FakePool()
    lima = RECEIVED_AT.astimezone(timezone(timedelta(hours=-5)))

    await ArqGatewayEventQueue(pool).enqueue(  # type: ignore[arg-type]
        event_id="A", raw_body=BODY, received_at=lima
    )

    assert pool.calls[0][0][2] == RECEIVED_AT_EPOCH


async def test_an_already_queued_job_id_is_not_an_error() -> None:
    # arq devuelve ``None`` cuando ya existe un trabajo con ese ``_job_id``.
    pool = FakePool(result=None)

    await ArqGatewayEventQueue(pool).enqueue(  # type: ignore[arg-type]
        event_id="A", raw_body=BODY, received_at=RECEIVED_AT
    )

    assert len(pool.calls) == 1


async def test_a_pool_failure_propagates_for_the_use_case_to_translate() -> None:
    pool = FakePool(error=ConnectionError("redis caido"))

    with pytest.raises(ConnectionError):
        await ArqGatewayEventQueue(pool).enqueue(  # type: ignore[arg-type]
            event_id="A", raw_body=BODY, received_at=RECEIVED_AT
        )


async def test_the_enqueued_arguments_bind_to_the_registered_job_signature(
    worker: ModuleType,
) -> None:
    pool = FakePool()
    await ArqGatewayEventQueue(pool).enqueue(  # type: ignore[arg-type]
        event_id="A", raw_body=BODY, received_at=RECEIVED_AT
    )
    name, *args = pool.calls[0][0]

    bound = inspect.signature(worker.process_gateway_event).bind({}, *args)

    assert name == PROCESS_GATEWAY_EVENT_JOB
    assert dict(bound.arguments) == {
        "ctx": {},
        "raw_body": BODY,
        "received_at_epoch": RECEIVED_AT_EPOCH,
    }
