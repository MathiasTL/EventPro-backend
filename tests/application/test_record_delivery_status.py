from datetime import timedelta

from structlog.testing import capture_logs

from app.application.use_cases.messaging.record_delivery_status import RecordDeliveryStatus
from app.domain.value_objects.outbox import DeliveryStatus
from tests.application.outbox_support import InMemoryOutboxStore
from tests.domain.outbox_support import NOW, make_message


def _store_with_sent_message() -> tuple[InMemoryOutboxStore, str]:
    store = InMemoryOutboxStore()
    message = make_message()
    message.mark_sent(external_message_id="cw-100", conversation_id=5, now=NOW)
    store.put(message)
    return store, str(message.id)


async def test_delivery_notice_updates_the_message_found_by_external_id() -> None:
    store, message_id = _store_with_sent_message()
    use_case = RecordDeliveryStatus(store.repository())

    applied = await use_case.execute(
        external_message_id="cw-100", status=DeliveryStatus.DELIVERED, error=None, at=NOW
    )

    assert applied is True
    stored = next(m for m in store.messages.values() if str(m.id) == message_id)
    assert stored.delivery_status is DeliveryStatus.DELIVERED
    assert stored.delivered_at == NOW


async def test_unknown_external_id_is_ignored_and_logged() -> None:
    store, _ = _store_with_sent_message()
    use_case = RecordDeliveryStatus(store.repository())

    with capture_logs() as logs:
        applied = await use_case.execute(
            external_message_id="manual-777", status=DeliveryStatus.READ, error=None, at=NOW
        )

    assert applied is False
    assert [entry["event"] for entry in logs] == ["outbox_delivery_unknown_message"]
    assert logs[0]["external_message_id"] == "manual-777"
    assert all(m.delivery_status is None for m in store.messages.values())


async def test_out_of_order_notice_is_ignored() -> None:
    store, _ = _store_with_sent_message()
    use_case = RecordDeliveryStatus(store.repository())
    await use_case.execute(
        external_message_id="cw-100", status=DeliveryStatus.READ, error=None, at=NOW
    )

    applied = await use_case.execute(
        external_message_id="cw-100",
        status=DeliveryStatus.DELIVERED,
        error=None,
        at=NOW + timedelta(minutes=1),
    )

    assert applied is False
    assert next(iter(store.messages.values())).delivery_status is DeliveryStatus.READ


async def test_failed_notice_keeps_the_reason_for_the_encargado() -> None:
    store, _ = _store_with_sent_message()
    await RecordDeliveryStatus(store.repository()).execute(
        external_message_id="cw-100",
        status=DeliveryStatus.FAILED,
        error="Número sin WhatsApp",
        at=NOW,
    )
    stored = next(iter(store.messages.values()))
    assert stored.delivery_status is DeliveryStatus.FAILED
    assert stored.delivery_error == "Número sin WhatsApp"


async def test_lookup_locks_the_row() -> None:
    store, _ = _store_with_sent_message()
    repository = store.repository()
    await RecordDeliveryStatus(repository).execute(
        external_message_id="cw-100", status=DeliveryStatus.DELIVERED, error=None, at=NOW
    )
    assert repository.for_update_requests == 1
