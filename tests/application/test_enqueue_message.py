from datetime import timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import MessageType, OutboxStatus
from tests.application.outbox_support import FixedClock, InMemoryOutboxStore
from tests.domain.outbox_support import NOW, PHONE, TEXT_PAYLOAD


async def test_enqueue_adds_a_pending_message_due_now_without_committing() -> None:
    store = InMemoryOutboxStore()
    use_case = EnqueueMessage(store.repository(), FixedClock())

    message = await use_case.execute(
        recipient=PHONE, message_type=MessageType.TEXT, payload=TEXT_PAYLOAD
    )

    stored = store.messages[message.id]
    assert stored.status is OutboxStatus.PENDING
    assert stored.next_attempt_at == NOW
    assert stored.recipient == PHONE
    assert stored.payload == TEXT_PAYLOAD
    assert store.commits == 0


async def test_enqueue_uses_the_clock_of_the_use_case() -> None:
    store = InMemoryOutboxStore()
    clock = FixedClock(NOW + timedelta(days=2))
    message = await EnqueueMessage(store.repository(), clock).execute(
        recipient=PHONE, message_type=MessageType.TEXT, payload=TEXT_PAYLOAD
    )
    assert message.created_at == NOW + timedelta(days=2)


async def test_enqueue_applies_the_configured_max_attempts_and_redaction() -> None:
    store = InMemoryOutboxStore()
    message = await EnqueueMessage(store.repository(), FixedClock(), max_attempts=3).execute(
        recipient=PHONE,
        message_type=MessageType.TEMPLATE,
        payload={"name": "otp", "params": {"codigo": "123456"}},
        redact_after_send=True,
    )
    assert message.max_attempts == 3
    assert message.redact_after_send is True


async def test_enqueue_rejects_an_incoherent_payload_and_stores_nothing() -> None:
    store = InMemoryOutboxStore()
    with pytest.raises(ValidationError):
        await EnqueueMessage(store.repository(), FixedClock()).execute(
            recipient=PHONE, message_type=MessageType.TEXT, payload={"name": "x"}
        )
    assert store.messages == {}


async def test_enqueue_records_the_author_and_defaults_to_no_author() -> None:
    store = InMemoryOutboxStore()
    use_case = EnqueueMessage(store.repository(), FixedClock())
    author = uuid4()

    authored = await use_case.execute(
        recipient=PHONE,
        message_type=MessageType.TEXT,
        payload=TEXT_PAYLOAD,
        author_user_id=author,
    )
    bot = await use_case.execute(
        recipient=PHONE, message_type=MessageType.TEXT, payload=TEXT_PAYLOAD
    )

    assert store.messages[authored.id].author_user_id == author
    assert store.messages[bot.id].author_user_id is None
