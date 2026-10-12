"""ReceiveGatewayEvent: reclamar el identificador, encolar y liberar si el encolado falla."""

from datetime import UTC, datetime

import pytest
from structlog.testing import capture_logs

from app.application.use_cases.messaging.errors import GatewayEventNotQueuedError
from app.application.use_cases.messaging.receive_gateway_event import (
    EVENT_DEDUP_TTL_SECONDS,
    ReceiveGatewayEvent,
)
from tests.application.gateway_event_support import InMemoryDedup, Queued, RecordingQueue

RECEIVED_AT = datetime(2026, 10, 12, 14, 1, tzinfo=UTC)
BODY = b'{"event": "message_updated", "id": 4821}'


def make(
    *, dedup: InMemoryDedup | None = None, queue: RecordingQueue | None = None
) -> tuple[ReceiveGatewayEvent, InMemoryDedup, RecordingQueue]:
    dedup = dedup or InMemoryDedup()
    queue = queue or RecordingQueue()
    return ReceiveGatewayEvent(dedup, queue), dedup, queue


async def test_the_first_sighting_is_claimed_and_enqueued() -> None:
    use_case, dedup, queue = make()

    queued = await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    assert queued is True
    assert queue.jobs == [Queued("A", BODY, RECEIVED_AT)]
    assert "A" in dedup.keys


def test_the_dedup_ttl_is_seven_days() -> None:
    assert EVENT_DEDUP_TTL_SECONDS == 604_800


async def test_the_claim_uses_the_seven_day_ttl() -> None:
    use_case, dedup, _ = make()

    await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    assert dedup.keys == {"A": 604_800}


async def test_a_duplicate_is_acknowledged_without_a_second_enqueue() -> None:
    use_case, _, queue = make()
    await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    queued = await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    assert queued is False
    assert len(queue.jobs) == 1


async def test_two_ids_with_identical_bodies_are_both_enqueued() -> None:
    use_case, _, queue = make()

    first = await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)
    second = await use_case.execute(event_id="B", raw_body=BODY, received_at=RECEIVED_AT)

    assert (first, second) == (True, True)
    assert [job.event_id for job in queue.jobs] == ["A", "B"]


async def test_an_enqueue_failure_releases_the_key_and_raises() -> None:
    use_case, dedup, queue = make(queue=RecordingQueue(fail=True))

    with pytest.raises(GatewayEventNotQueuedError) as caught:
        await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    assert (caught.value.event_id, caught.value.error_type) == ("A", "ConnectionError")
    assert dedup.released == ["A"]
    assert dedup.keys == {}
    assert queue.jobs == []


async def test_after_a_failed_enqueue_a_resend_of_the_same_id_is_queued() -> None:
    dedup = InMemoryDedup()
    failing = ReceiveGatewayEvent(dedup, RecordingQueue(fail=True))
    with pytest.raises(GatewayEventNotQueuedError):
        await failing.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)
    queue = RecordingQueue()

    queued = await ReceiveGatewayEvent(dedup, queue).execute(
        event_id="A", raw_body=BODY, received_at=RECEIVED_AT
    )

    assert queued is True
    assert [job.event_id for job in queue.jobs] == ["A"]


async def test_a_claim_failure_raises_and_enqueues_nothing() -> None:
    use_case, dedup, queue = make(dedup=InMemoryDedup(fail_claim=True))

    with pytest.raises(GatewayEventNotQueuedError) as caught:
        await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    assert caught.value.error_type == "ConnectionError"
    assert queue.jobs == []
    assert dedup.released == []


async def test_a_release_failure_still_raises_the_not_queued_error_and_is_logged() -> None:
    use_case, _, _ = make(dedup=InMemoryDedup(fail_release=True), queue=RecordingQueue(fail=True))

    with capture_logs() as logs, pytest.raises(GatewayEventNotQueuedError) as caught:
        await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    assert caught.value.error_type == "ConnectionError"
    assert logs == [
        {
            "event": "gateway_event_release_failed",
            "log_level": "warning",
            "error_type": "ConnectionError",
        }
    ]


async def test_the_release_failure_log_never_carries_the_id_or_the_body() -> None:
    use_case, _, _ = make(dedup=InMemoryDedup(fail_release=True), queue=RecordingQueue(fail=True))

    with capture_logs() as logs, pytest.raises(GatewayEventNotQueuedError):
        await use_case.execute(event_id="A", raw_body=BODY, received_at=RECEIVED_AT)

    assert logs
    assert "4821" not in repr(logs)
    # El id puede ser el resumen de la firma (si Chatwoot no envía el encabezado de entrega).
    assert "event_id" not in repr(logs)
