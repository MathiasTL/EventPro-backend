"""Enviar y reintentar desde la bandeja (spec 09, 6.4, 6.7, D6, D20, D24)."""

from datetime import timedelta
from uuid import UUID

import pytest

from app.application.dtos.messaging_dto import AuthorType, MessageDirection, MessageSender
from app.application.services.audit_service import AuditService
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.application.use_cases.messaging.message_authorship import resolve_author_type
from app.application.use_cases.messaging.retry_message import RetryMessage
from app.application.use_cases.messaging.send_conversation_message import (
    RetryConversationMessage,
    SendConversationMessage,
)
from app.domain.exceptions.messaging_exceptions import (
    ConversationNotTakenError,
    ConversationTakenByOtherError,
    ConversationWindowClosedError,
)
from app.domain.exceptions.outbox_exceptions import (
    InvalidOutboxStateError,
    OutboxMessageNotFoundError,
)
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import DeliveryStatus, MessageType, OutboxStatus
from tests.application.assignment_support import NOW, PHONE, AssignmentWorld, new_user
from tests.application.outbox_support import FixedClock, InMemoryOutboxStore
from tests.domain.outbox_support import DOCUMENT_PAYLOAD, make_message


class _World(AssignmentWorld):
    def __init__(self) -> None:
        super().__init__()
        self.store = InMemoryOutboxStore()
        self.clock = FixedClock(NOW)
        self.outbox = self.store.repository()
        self.send = self._build_send(AuditService(self.audit_port))
        self.retry = RetryConversationMessage(
            self.messaging,
            self.links,
            self.outbox,
            AuditService(self.audit_port),
            RetryMessage(self.outbox, self.clock),
        )

    def _build_send(self, audit: AuditService) -> SendConversationMessage:
        return SendConversationMessage(
            self.messaging,
            self.links,
            self.outbox,
            audit,
            EnqueueMessage(self.outbox, self.clock),
        )

    def failed_row(self, user: UUID, *, delivery_rejected: bool = False) -> UUID:
        message = make_message(recipient=PHONE, author_user_id=user)
        if delivery_rejected:
            message.mark_sent(external_message_id="cw-9", conversation_id=1, now=NOW)
            message.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW)
        else:
            message.register_failure(error="caído", permanent=True, now=NOW)
        self.store.put(message)
        return message.id


@pytest.fixture
def world() -> _World:
    return _World()


# --- send -----------------------------------------------------------------------------


async def test_send_enqueues_text_with_the_author_and_audits_without_content(
    world: _World,
) -> None:
    user = new_user()
    await world.assign(user)

    queued = await world.send.execute(1, user_id=user, content="Claro, con gusto")

    row = world.store.messages[queued.outbox_id]
    assert (row.message_type, row.payload, row.recipient) == (
        MessageType.TEXT,
        {"body": "Claro, con gusto"},
        PHONE,
    )
    assert row.author_user_id == user
    assert queued.chatwoot_conversation_id == 1
    (entry,) = world.audit_port.entries
    assert (entry.action, entry.entity_name, entry.entity_id, entry.user_id) == (
        "SEND_CONVERSATION_MESSAGE",
        "outbox_message",
        row.id,
        user,
    )
    assert entry.new_values == {"message_type": "TEXT", "conversation_id": 1}
    assert "Claro" not in repr(entry)


async def test_send_does_not_change_the_assignment_or_publish(world: _World) -> None:
    user = new_user()
    await world.assign(user)

    await world.send.execute(1, user_id=user, content="Hola")

    assert world.stored().assigned_user_id == user
    assert world.publisher.events == []


async def test_send_enqueues_a_document(world: _World) -> None:
    user = new_user()
    await world.assign(user)

    queued = await world.send.execute(1, user_id=user, document=DOCUMENT_PAYLOAD)

    row = world.store.messages[queued.outbox_id]
    assert row.message_type is MessageType.DOCUMENT
    assert row.author_user_id == user


@pytest.mark.parametrize(
    ("content", "document"),
    [(None, None), ("   ", None), ("Hola", DOCUMENT_PAYLOAD)],
)
async def test_send_requires_exactly_text_or_document(
    world: _World, content: str | None, document: dict[str, object] | None
) -> None:
    user = new_user()
    await world.assign(user)

    with pytest.raises(ValidationError):
        await world.send.execute(1, user_id=user, content=content, document=document)

    assert world.store.messages == {}


async def test_send_on_a_conversation_with_the_bot_is_not_taken(world: _World) -> None:
    with pytest.raises(ConversationNotTakenError):
        await world.send.execute(1, user_id=new_user(), content="Hola")


async def test_send_on_an_open_unassigned_conversation_is_not_taken(world: _World) -> None:
    await world.open_unassigned()

    with pytest.raises(ConversationNotTakenError):
        await world.send.execute(1, user_id=new_user(), content="Hola")

    assert world.store.messages == {}


async def test_send_on_a_conversation_of_another_agent_reports_the_assignee(
    world: _World,
) -> None:
    owner = new_user()
    await world.assign(owner)

    with pytest.raises(ConversationTakenByOtherError) as raised:
        await world.send.execute(1, user_id=new_user(), content="Hola")

    assert raised.value.assigned_user_id == owner
    assert world.store.messages == {}


async def test_send_with_the_window_closed_reports_when_it_expired(world: _World) -> None:
    user = new_user()
    await world.assign(user)
    link = world.stored()
    link.last_client_message_at = NOW - timedelta(hours=30)
    world.links.put(link)
    world.messaging.service_window_open = False

    with pytest.raises(ConversationWindowClosedError) as raised:
        await world.send.execute(1, user_id=user, content="Hola")

    assert raised.value.expires_at == NOW - timedelta(hours=6)
    assert world.store.messages == {}
    assert world.audit_port.entries == []


class _FailingAudit:
    async def record(self, entry: object) -> None:
        raise RuntimeError("auditoría caída")


async def test_a_failed_audit_rolls_back_the_enqueue(world: _World) -> None:
    user = new_user()
    await world.assign(user)

    with pytest.raises(RuntimeError):
        async with world.store.transaction() as outbox:
            send = SendConversationMessage(
                world.messaging,
                world.links,
                outbox,
                AuditService(_FailingAudit()),
                EnqueueMessage(outbox, world.clock),
            )
            await send.execute(1, user_id=user, content="Hola")

    assert world.store.messages == {}


# --- retry ----------------------------------------------------------------------------


async def test_retry_requeues_the_same_row_and_audits_retry_of(world: _World) -> None:
    user = new_user()
    await world.assign(user)
    row_id = world.failed_row(user)

    queued = await world.retry.execute(1, row_id, user_id=user)

    assert queued.outbox_id == row_id
    row = world.store.messages[row_id]
    assert (row.status, row.attempts) == (OutboxStatus.PENDING, 0)
    assert len(world.store.messages) == 1
    (entry,) = world.audit_port.entries
    assert entry.entity_id == row_id
    assert entry.new_values == {
        "message_type": "TEXT",
        "conversation_id": 1,
        "retry_of": str(row_id),
    }


async def test_retry_keeps_authorship_of_the_original_failed_message(world: _World) -> None:
    user = new_user()
    await world.assign(user)
    row_id = world.failed_row(user, delivery_rejected=True)

    await world.retry.execute(1, row_id, user_id=user)

    row = world.store.messages[row_id]
    assert row.external_message_id is None
    assert row.retried_external_message_id == "cw-9"
    found = await world.outbox.get_many_by_external_ids(["cw-9"])
    assert found["cw-9"].id == row_id
    assert (
        resolve_author_type(
            direction=MessageDirection.OUTGOING,
            outbox=found["cw-9"],
            sender=MessageSender.AGENT_BOT,
        )
        is AuthorType.AGENT
    )


@pytest.mark.parametrize("sent", [True, False])
async def test_retry_of_a_healthy_row_is_an_invalid_state(world: _World, sent: bool) -> None:
    user = new_user()
    await world.assign(user)
    message = make_message(recipient=PHONE, author_user_id=user)
    if sent:
        message.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    world.store.put(message)

    with pytest.raises(InvalidOutboxStateError):
        await world.retry.execute(1, message.id, user_id=user)

    assert world.audit_port.entries == []


async def test_retry_of_a_redacted_row_is_an_invalid_state(world: _World) -> None:
    user = new_user()
    await world.assign(user)
    message = make_message(recipient=PHONE, redact_after_send=True)
    message.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    message.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW)
    world.store.put(message)

    with pytest.raises(InvalidOutboxStateError):
        await world.retry.execute(1, message.id, user_id=user)


async def test_retry_of_a_missing_or_foreign_row_is_not_found(world: _World) -> None:
    user = new_user()
    await world.assign(user)
    foreign = make_message()
    foreign.register_failure(error="x", permanent=True, now=NOW)
    world.store.put(foreign)

    with pytest.raises(OutboxMessageNotFoundError):
        await world.retry.execute(1, foreign.id, user_id=user)
    with pytest.raises(OutboxMessageNotFoundError):
        await world.retry.execute(1, UUID(int=1), user_id=user)


async def test_retry_requires_the_conversation_to_be_taken_by_the_user(world: _World) -> None:
    owner = new_user()
    await world.assign(owner)
    row_id = world.failed_row(owner)

    with pytest.raises(ConversationTakenByOtherError):
        await world.retry.execute(1, row_id, user_id=new_user())

    assert world.store.messages[row_id].status is OutboxStatus.FAILED


async def test_retry_with_the_window_closed_changes_nothing(world: _World) -> None:
    user = new_user()
    await world.assign(user)
    row_id = world.failed_row(user)
    world.messaging.service_window_open = False

    with pytest.raises(ConversationWindowClosedError):
        await world.retry.execute(1, row_id, user_id=user)

    assert world.store.messages[row_id].status is OutboxStatus.FAILED
    assert world.audit_port.entries == []
