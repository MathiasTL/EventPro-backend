"""ProcessGatewayEvent con la bandeja: vínculo, eventos y reglas de enrutamiento (spec 09, 6.1)."""

from datetime import timedelta
from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from app.application.dtos.conversation_event_dto import ConversationEvent, ConversationEventType
from app.application.dtos.gateway_event_dto import (
    ConversationSnapshot,
    DeliveryNotice,
    GatewayEvent,
    GatewayEventOutcome,
    IncomingClientMessage,
    MessageDetails,
    OutgoingMessageEcho,
)
from app.application.dtos.messaging_dto import (
    ConversationLifecycle,
    ConversationStatus,
    MessageAttachment,
    MessageSender,
)
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.domain.entities.client import Client
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.outbox import DeliveryStatus
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.events.in_memory_conversation_event_publisher import (
    InMemoryConversationEventPublisher,
)
from tests.application.inbox_event_support import InMemoryClients, InMemoryInbox
from tests.application.outbox_support import InMemoryOutboxStore
from tests.domain.outbox_support import NOW, make_message

CONVERSATION_ID = 57
EXTERNAL_ID = "4830"
PHONE = PhoneNumber("+51999888777")
RECEIVED_AT = NOW + timedelta(seconds=30)
SENT_AT = NOW + timedelta(seconds=10)
RAW_BODY = b"{}"


class _Gateway:
    def __init__(self, event: GatewayEvent) -> None:
        self._event = event

    def parse_event(self, raw_body: bytes) -> GatewayEvent:
        return self._event

    async def get_delivery_status(self, conversation_id: int, external_message_id: str) -> None:
        return None


class _Bot:
    def __init__(self) -> None:
        self.messages: list[IncomingClientMessage] = []

    async def execute(self, message: IncomingClientMessage) -> GatewayEventOutcome:
        self.messages.append(message)
        return GatewayEventOutcome.APPLIED


def _snapshot(
    lifecycle: ConversationLifecycle = ConversationLifecycle.OPEN,
    *,
    phone: PhoneNumber | None = PHONE,
) -> ConversationSnapshot:
    return ConversationSnapshot(
        lifecycle=lifecycle,
        unread_count=2,
        can_reply=True,
        contact_phone=phone,
        contact_name="Perfil WhatsApp",
    )


def _incoming(
    status: ConversationStatus = ConversationStatus.HUMAN, **overrides: object
) -> IncomingClientMessage:
    lifecycle = (
        ConversationLifecycle.PENDING
        if status is ConversationStatus.BOT
        else ConversationLifecycle.OPEN
    )
    values: dict[str, object] = {
        "external_message_id": EXTERNAL_ID,
        "conversation_id": CONVERSATION_ID,
        "conversation_status": status,
        "sender_phone": PHONE,
        "content": "Hola, quiero cotizar",
        "snapshot": _snapshot(lifecycle),
        "details": MessageDetails(sent_at=SENT_AT),
    }
    values.update(overrides)
    return IncomingClientMessage(**values)  # type: ignore[arg-type]


def _echo(**overrides: object) -> OutgoingMessageEcho:
    values: dict[str, object] = {
        "external_message_id": EXTERNAL_ID,
        "conversation_id": CONVERSATION_ID,
        "content": "Claro, con gusto",
        "snapshot": _snapshot(),
        "details": MessageDetails(sent_at=SENT_AT, sender=MessageSender.AGENT_BOT),
    }
    values.update(overrides)
    return OutgoingMessageEcho(**values)  # type: ignore[arg-type]


class _World:
    def __init__(
        self,
        event: GatewayEvent,
        *,
        client: Client | None = None,
        publish_error: Exception | None = None,
    ) -> None:
        self.store = InMemoryOutboxStore()
        self.inbox = InMemoryInbox(
            self.store, clients=InMemoryClients(*([client] if client else []))
        )
        self.publisher = InMemoryConversationEventPublisher(error=publish_error)
        self.bot = _Bot()
        self.use_case = ProcessGatewayEvent(
            transaction=lambda: self.store.transaction(),
            gateway=_Gateway(event),
            incoming_handler=self.bot,
            inbox=self.inbox,
            publisher=self.publisher,
        )

    async def run(self, *, last_attempt: bool = False) -> GatewayEventOutcome:
        return await self.use_case.execute(
            raw_body=RAW_BODY, received_at=RECEIVED_AT, last_attempt=last_attempt
        )

    def names(self) -> list[str]:
        return [e.event.value for e in self.publisher.events]

    def message(self, index: int = 0) -> dict[str, object]:
        data = self.publisher.events[index].data
        message: dict[str, object] = data["message"]
        return message


# --- Entrantes ----------------------------------------------------------------------------


async def test_an_incoming_message_in_open_is_published_and_never_reaches_the_bot() -> None:
    world = _World(_incoming(ConversationStatus.HUMAN))

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    assert world.bot.messages == []
    assert world.names() == ["message.created", "conversation.updated"]
    assert world.message()["author_type"] == "CLIENT"
    assert world.message()["content"] == "Hola, quiero cotizar"
    assert world.message()["delivery_status"] is None


async def test_an_incoming_message_in_pending_is_published_and_still_goes_to_the_bot() -> None:
    message = _incoming(ConversationStatus.BOT)
    world = _World(message)

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    assert world.bot.messages == [message]
    assert world.names() == ["message.created", "conversation.updated"]


async def test_an_incoming_message_creates_the_link_and_marks_the_client_time() -> None:
    world = _World(_incoming())

    await world.run()

    link = world.inbox.links.links[CONVERSATION_ID]
    assert link.last_client_message_at == SENT_AT
    assert link.client_id is None


async def test_the_link_gets_the_client_when_the_phone_matches_and_no_client_is_created() -> None:
    client = Client(phone=PHONE, full_name="Carlos Ramírez")
    world = _World(_incoming(), client=client)

    await world.run()

    assert world.inbox.links.links[CONVERSATION_ID].client_id == client.id
    assert len(world.inbox.clients.clients) == 1
    item = world.publisher.events[1].data
    assert item["client"] == {"id": str(client.id), "name": "Carlos Ramírez", "phone": PHONE.value}


async def test_an_existing_link_without_client_is_completed_when_the_client_appears() -> None:
    client = Client(phone=PHONE, full_name="Carlos Ramírez")
    world = _World(_incoming(), client=client)
    await world.inbox.links.ensure(CONVERSATION_ID, None, NOW)

    await world.run()

    assert world.inbox.links.links[CONVERSATION_ID].client_id == client.id


async def test_the_conversation_item_carries_mode_unread_and_window() -> None:
    world = _World(_incoming())

    await world.run()

    item = world.publisher.events[1].data
    assert item["chatwoot_conversation_id"] == CONVERSATION_ID
    assert (item["status"], item["mode"], item["unread_count"]) == ("open", "HUMAN", 2)
    assert item["client"] == {"id": None, "name": "Perfil WhatsApp", "phone": PHONE.value}
    assert item["last_message_preview"] == "Hola, quiero cotizar"
    assert item["service_window_open"] is True
    assert item["service_window_expires_at"] == "2026-10-10T15:00:10Z"
    assert "lead_status" not in item


async def test_an_attachment_only_message_previews_as_attachment() -> None:
    details = MessageDetails(
        sent_at=SENT_AT, attachments=(MessageAttachment(311, "image", "image/jpeg"),)
    )
    world = _World(_incoming(content="", details=details))

    await world.run()

    assert world.publisher.events[1].data["last_message_preview"] == "[Adjunto]"
    assert world.message()["attachments"] == [
        {
            "id": 311,
            "file_type": "image",
            "content_type": "image/jpeg",
            "url": "/api/v1/conversations/57/attachments/311",
        }
    ]


async def test_a_message_without_time_uses_the_signed_reception_time() -> None:
    world = _World(_incoming(details=MessageDetails()))

    await world.run()

    assert world.inbox.links.links[CONVERSATION_ID].last_client_message_at == RECEIVED_AT


async def test_a_private_incoming_message_is_not_recorded_nor_published() -> None:
    world = _World(_incoming(ConversationStatus.BOT, is_private=True))

    await world.run()

    assert world.inbox.links.links == {}
    assert world.publisher.events == []
    assert len(world.bot.messages) == 1


async def test_a_publish_failure_is_logged_and_the_bot_still_answers() -> None:
    world = _World(_incoming(ConversationStatus.BOT), publish_error=ConnectionError("redis caido"))

    with capture_logs() as logs:
        outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    assert len(world.bot.messages) == 1
    failures = [e for e in logs if e["event"] == "conversation_event_publish_failed"]
    assert [f["error_type"] for f in failures] == ["ConnectionError", "ConnectionError"]
    assert all("redis caido" not in str(entry) for entry in logs)


async def test_a_failure_recording_the_link_never_blocks_the_bot() -> None:
    world = _World(_incoming(ConversationStatus.BOT))

    async def broken(*_: object) -> None:
        raise ResourceNotFoundError("base caída")

    world.inbox.links.ensure = broken  # type: ignore[method-assign]

    with capture_logs() as logs:
        outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    assert len(world.bot.messages) == 1
    assert world.publisher.events == []
    assert [e["event"] for e in logs] == ["inbox_record_failed"]


async def test_without_the_inbox_an_incoming_message_keeps_going_to_the_bot() -> None:
    message = _incoming(ConversationStatus.HUMAN)
    store = InMemoryOutboxStore()
    bot = _Bot()
    use_case = ProcessGatewayEvent(
        transaction=lambda: store.transaction(), gateway=_Gateway(message), incoming_handler=bot
    )

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert bot.messages == [message]


# --- Ecos salientes -----------------------------------------------------------------------


async def test_an_echo_of_an_agent_message_is_published_with_the_agent_author() -> None:
    row = make_message(author_user_id=uuid4())
    row.mark_sent(external_message_id=EXTERNAL_ID, conversation_id=CONVERSATION_ID, now=NOW)
    world = _World(_echo())
    world.store.put(row)

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    assert world.names() == ["message.created", "conversation.updated"]
    assert world.message()["author_type"] == "AGENT"
    assert world.message()["outbox_id"] == str(row.id)
    assert world.message()["delivery_status"] == "SENT"
    # Un saliente no mueve la marca de tiempo del cliente.
    assert world.inbox.links.links[CONVERSATION_ID].last_client_message_at is None


async def test_an_echo_of_a_bot_row_is_published_as_bot_even_if_chatwoot_says_user() -> None:
    row = make_message()
    row.mark_sent(external_message_id=EXTERNAL_ID, conversation_id=CONVERSATION_ID, now=NOW)
    details = MessageDetails(sent_at=SENT_AT, sender=MessageSender.USER)
    world = _World(_echo(details=details))
    world.store.put(row)

    await world.run()

    assert world.message()["author_type"] == "BOT"


async def test_an_echo_is_matched_by_the_external_id_kept_after_a_retry() -> None:
    row = make_message(author_user_id=uuid4())
    row.retried_external_message_id = EXTERNAL_ID
    world = _World(_echo())
    world.store.put(row)

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    assert world.message()["author_type"] == "AGENT"


async def test_an_echo_without_an_outbox_row_waits_for_it_while_attempts_remain() -> None:
    world = _World(_echo())

    outcome = await world.run(last_attempt=False)

    assert outcome is GatewayEventOutcome.UNKNOWN_MESSAGE
    assert world.publisher.events == []
    assert world.inbox.links.links == {}


@pytest.mark.parametrize(
    ("sender", "author"),
    [(MessageSender.USER, "AGENT"), (MessageSender.AGENT_BOT, "BOT"), (None, "BOT")],
)
async def test_the_last_attempt_publishes_an_unmatched_echo_by_its_sender(
    sender: MessageSender | None, author: str
) -> None:
    world = _World(_echo(details=MessageDetails(sent_at=SENT_AT, sender=sender)))

    with capture_logs() as logs:
        outcome = await world.run(last_attempt=True)

    assert outcome is GatewayEventOutcome.APPLIED
    assert world.message()["author_type"] == author
    assert world.message()["outbox_id"] is None
    assert [e["event"] for e in logs] == ["echo_without_outbox_row"]


async def test_an_echo_already_rejected_by_chatwoot_publishes_the_translated_reason() -> None:
    error = "La ventana de atención al cliente de WhatsApp de 24 horas está cerrada."
    details = MessageDetails(
        sent_at=SENT_AT,
        sender=MessageSender.AGENT_BOT,
        delivery_status=DeliveryStatus.FAILED,
        error=error,
    )
    world = _World(_echo(details=details))

    await world.run(last_attempt=True)

    message = world.message()
    assert message["delivery_status"] == "FAILED"
    assert (
        message["failure_reason"] == "Han pasado más de 24 horas; el cliente debe escribir primero."
    )
    assert message["failure_code"] is None
    assert error not in str(world.publisher.events)


async def test_without_the_inbox_an_echo_is_only_logged() -> None:
    store = InMemoryOutboxStore()
    use_case = ProcessGatewayEvent(
        transaction=lambda: store.transaction(), gateway=_Gateway(_echo())
    )

    with capture_logs() as logs:
        outcome = await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    assert outcome is GatewayEventOutcome.UNHANDLED
    assert [e["event"] for e in logs] == ["gateway_event_unhandled"]


# --- Avisos de entrega --------------------------------------------------------------------


def _notice(**overrides: object) -> DeliveryNotice:
    values: dict[str, object] = {
        "external_message_id": EXTERNAL_ID,
        "conversation_id": CONVERSATION_ID,
        "status": DeliveryStatus.FAILED,
        "error": "(#131030) Recipient phone number not in allowed list",
        "updated_at": SENT_AT,
        "status_in_payload": True,
    }
    values.update(overrides)
    return DeliveryNotice(**values)  # type: ignore[arg-type]


def _world_with_sent_row(
    notice: DeliveryNotice, *, publish_error: Exception | None = None
) -> _World:
    row = make_message(author_user_id=uuid4())
    row.mark_sent(external_message_id=EXTERNAL_ID, conversation_id=CONVERSATION_ID, now=NOW)
    world = _World(notice, publish_error=publish_error)
    world.store.put(row)
    return world


async def test_an_applied_failure_publishes_message_updated_with_a_translated_reason() -> None:
    world = _world_with_sent_row(_notice())

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    assert world.names() == ["message.updated"]
    assert world.publisher.events[0].data == {
        "chatwoot_conversation_id": CONVERSATION_ID,
        "message": {
            "id": 4830,
            "delivery_status": "FAILED",
            "failure_reason": "El número no está entre los destinatarios de prueba.",
            "failure_code": 131030,
            "outbox_id": str(next(iter(world.store.messages))),
            "retryable": True,
        },
    }
    assert "Recipient" not in str(world.publisher.events)


async def test_an_applied_delivery_publishes_the_status_without_failure() -> None:
    world = _world_with_sent_row(_notice(status=DeliveryStatus.DELIVERED, error=None))

    await world.run()

    message = world.message()
    assert (message["delivery_status"], message["failure_reason"]) == ("DELIVERED", None)
    assert message["retryable"] is False


async def test_a_notice_that_changes_nothing_publishes_nothing() -> None:
    world = _world_with_sent_row(_notice(status=DeliveryStatus.READ, error=None))
    await world.run()
    world.publisher.events.clear()

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.IGNORED
    assert world.publisher.events == []


async def test_a_notice_for_an_unknown_message_publishes_nothing() -> None:
    world = _World(_notice())

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.UNKNOWN_MESSAGE
    assert world.publisher.events == []


async def test_a_publish_failure_never_fails_the_delivery_notice() -> None:
    world = _world_with_sent_row(_notice(), publish_error=ConnectionError("redis caido"))

    outcome = await world.run()

    assert outcome is GatewayEventOutcome.APPLIED
    (stored,) = world.store.messages.values()
    assert stored.delivery_status is DeliveryStatus.FAILED


def test_the_envelope_is_versioned_and_json_ready() -> None:
    event = ConversationEvent(
        ConversationEventType.MESSAGE_UPDATED, {"chatwoot_conversation_id": 1}
    )

    assert event.to_envelope() == {
        "v": 1,
        "event": "message.updated",
        "data": {"chatwoot_conversation_id": 1},
    }


async def test_the_in_memory_publisher_keeps_the_order() -> None:
    publisher = InMemoryConversationEventPublisher()
    first = ConversationEvent(ConversationEventType.MESSAGE_CREATED, {})
    second = ConversationEvent(ConversationEventType.CONVERSATION_UPDATED, {})

    await publisher.publish(first)
    await publisher.publish(second)

    assert publisher.events == [first, second]
