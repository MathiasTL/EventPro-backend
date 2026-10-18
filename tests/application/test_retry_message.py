from datetime import timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.messaging.retry_message import RetryMessage
from app.domain.exceptions.outbox_exceptions import InvalidOutboxStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.outbox import DeliveryStatus, OutboxStatus
from tests.application.outbox_support import FixedClock, InMemoryOutboxStore
from tests.domain.outbox_support import NOW, make_message


async def test_retry_requeues_a_failed_message_due_now() -> None:
    store = InMemoryOutboxStore()
    message = make_message()
    message.register_failure(error="ventana cerrada", permanent=True, now=NOW)
    store.put(message)
    clock = FixedClock(NOW + timedelta(hours=3))

    result = await RetryMessage(store.repository(), clock).execute(message.id)

    assert result.status is OutboxStatus.PENDING
    stored = store.messages[message.id]
    assert stored.attempts == 0
    assert stored.next_attempt_at == NOW + timedelta(hours=3)


async def test_retry_requeues_a_message_rejected_by_whatsapp() -> None:
    store = InMemoryOutboxStore()
    message = make_message()
    message.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    message.record_delivery(status=DeliveryStatus.FAILED, error="Sin WhatsApp", at=NOW)
    store.put(message)

    await RetryMessage(store.repository(), FixedClock()).execute(message.id)

    stored = store.messages[message.id]
    assert stored.status is OutboxStatus.PENDING
    assert stored.delivery_status is None


async def test_retry_of_a_missing_message_raises_not_found() -> None:
    store = InMemoryOutboxStore()
    with pytest.raises(ResourceNotFoundError):
        await RetryMessage(store.repository(), FixedClock()).execute(uuid4())


async def test_retry_of_a_healthy_message_raises_and_changes_nothing() -> None:
    store = InMemoryOutboxStore()
    message = make_message()
    message.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    store.put(message)

    with pytest.raises(InvalidOutboxStateError):
        await RetryMessage(store.repository(), FixedClock()).execute(message.id)

    assert store.messages[message.id].status is OutboxStatus.SENT
