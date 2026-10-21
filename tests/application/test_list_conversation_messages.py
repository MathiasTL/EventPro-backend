"""ListConversationMessages: autoría, fallas, reintento y ``unsent`` (spec 09, 4.3 y 7.3)."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.application.dtos.messaging_dto import AuthorType, MessageDirection
from app.application.use_cases.messaging.failure_catalog import (
    GENERIC_SEND_REASON,
    MESSAGING_UNAVAILABLE_REASON,
    WINDOW_CLOSED_REASON,
)
from app.application.use_cases.messaging.list_conversation_messages import (
    ListConversationMessages,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.outbox import DeliveryStatus, MessageType
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from tests.application.inbox_read_support import FakeInboxLookup
from tests.application.outbox_support import InMemoryOutboxStore
from tests.domain.outbox_support import NOW, make_message

PHONE = PhoneNumber("+51999888777")
MARIA = uuid4()


class _World:
    def __init__(self) -> None:
        self.messaging = FakeMessagingAdapter()
        self.store = InMemoryOutboxStore()
        self.outbox = self.store.repository()
        self.lookup = FakeInboxLookup(users={MARIA: "María Torres"})
        self.use_case = ListConversationMessages(self.messaging, self.outbox, self.lookup)
        self.incoming = self.messaging.receive_text(PHONE, "Hola, quiero cotizar", name="Carlos")
        self.conversation = 1

    async def send(self, body: str) -> str:
        receipt = await self.messaging.send_text(PHONE, body)
        return receipt.message_id

    def patch(self, message_id: str, **fields: object) -> None:
        messages = self.messaging._conversations[self.conversation].messages
        index = next(i for i, m in enumerate(messages) if m.message_id == message_id)
        messages[index] = replace(messages[index], **fields)

    def agent_row(self, message_id: str, **overrides: object):  # type: ignore[no-untyped-def]
        message = make_message(author_user_id=MARIA, recipient=PHONE, **overrides)
        message.mark_sent(external_message_id=message_id, conversation_id=1, now=NOW)
        return self.store.put(message)


async def test_it_lists_newest_first_with_author_resolution() -> None:
    world = _World()
    bot_id = await world.send("Te cotizo enseguida")
    agent_id = await world.send("Claro, con gusto")
    world.agent_row(agent_id)

    page = await world.use_case.execute(1)

    assert [m.id for m in page.items] == [int(agent_id), int(bot_id), world.incoming]
    agent, bot, client = page.items
    assert (agent.author_type, agent.author_name) == (AuthorType.AGENT, "María Torres")
    assert agent.outbox_id is not None
    # Sin fila de outbox gana el remitente de Chatwoot: el Agent Bot es el bot, sin nombre.
    assert (bot.author_type, bot.author_name, bot.outbox_id) == (AuthorType.BOT, None, None)
    assert (client.author_type, client.direction) == (AuthorType.CLIENT, MessageDirection.INCOMING)
    assert client.delivery_status is None


async def test_an_outbox_row_without_author_is_the_bot() -> None:
    world = _World()
    message_id = await world.send("Hola")
    row = make_message(recipient=PHONE)
    row.mark_sent(external_message_id=message_id, conversation_id=1, now=NOW)
    world.store.put(row)

    page = await world.use_case.execute(1)

    assert page.items[0].author_type is AuthorType.BOT


async def test_it_translates_failures_and_marks_failed_rows_retryable() -> None:
    world = _World()
    message_id = await world.send("Mensaje")
    world.patch(
        message_id,
        status="failed",
        external_error="(#131030) Recipient phone number not in allowed list",
    )
    row = world.agent_row(message_id)
    row.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW)
    world.store.put(row)

    (failed, _) = (await world.use_case.execute(1)).items

    assert failed.delivery_status == "FAILED"
    assert failed.failure_code == 131030
    assert failed.failure_reason == "El número no está entre los destinatarios de prueba."
    assert failed.retryable is True
    assert "Recipient" not in (failed.failure_reason or "")


async def test_a_retried_message_keeps_its_author_but_loses_the_retry_button() -> None:
    world = _World()
    message_id = await world.send("Mensaje")
    world.patch(message_id, status="failed", external_error=None)
    row = world.agent_row(message_id)
    row.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW)
    row.retry(now=NOW)
    row.retried_external_message_id = message_id
    world.store.put(row)

    (old, _) = (await world.use_case.execute(1)).items

    assert old.author_type is AuthorType.AGENT
    assert old.retryable is False
    assert old.failure_reason == "No se pudo entregar el mensaje."


async def test_it_paginates_with_an_id_cursor_and_reports_has_more() -> None:
    world = _World()
    ids = [await world.send(f"m{n}") for n in range(4)]

    first = await world.use_case.execute(1, limit=2)
    second = await world.use_case.execute(1, before_id=int(ids[2]), limit=2)

    assert [m.id for m in first.items] == [int(ids[3]), int(ids[2])]
    assert first.has_more is True
    assert [m.id for m in second.items] == [int(ids[1]), int(ids[0])]
    assert second.has_more is True
    last = await world.use_case.execute(1, before_id=int(ids[0]), limit=2)
    assert [m.id for m in last.items] == [world.incoming]
    assert last.has_more is False


async def test_unsent_only_comes_on_the_first_page() -> None:
    world = _World()
    queued = make_message(author_user_id=MARIA, recipient=PHONE)
    failed = make_message(recipient=PHONE, message_type=MessageType.TEXT)
    failed.register_failure(error="ServiceWindowClosedError: x", permanent=True, now=NOW)
    unavailable = make_message(recipient=PHONE)
    unavailable.register_failure(error="MessagingUnavailableError: x", permanent=True, now=NOW)
    odd = make_message(recipient=PHONE)
    odd.register_failure(error="Boom", permanent=True, now=NOW)
    other_recipient = make_message(recipient=PhoneNumber("+51900000000"))
    for row in (queued, failed, unavailable, odd, other_recipient):
        world.store.put(row)

    first = await world.use_case.execute(1)
    older = await world.use_case.execute(1, before_id=world.incoming + 1)

    assert older.unsent is None
    assert first.unsent is not None
    by_id = {u.outbox_id: u for u in first.unsent}
    assert set(by_id) == {queued.id, failed.id, unavailable.id, odd.id}
    q = by_id[queued.id]
    assert (q.delivery_status, q.failure_reason, q.retryable) == ("QUEUED", None, False)
    assert (q.author_type, q.author_name) == (AuthorType.AGENT, "María Torres")
    assert by_id[failed.id].failure_reason == WINDOW_CLOSED_REASON
    assert by_id[failed.id].retryable is True
    assert by_id[failed.id].author_type is AuthorType.BOT
    assert by_id[unavailable.id].failure_reason == MESSAGING_UNAVAILABLE_REASON
    assert by_id[odd.id].failure_reason == GENERIC_SEND_REASON


async def test_it_reads_the_outbox_and_user_names_once() -> None:
    world = _World()
    for n in range(3):
        world.agent_row(await world.send(f"m{n}"))

    await world.use_case.execute(1)

    assert world.outbox.batch_lookups == 1
    assert world.lookup.calls == ["user_names"]


async def test_activity_notices_have_no_author() -> None:
    world = _World()
    world.messaging.add_activity(1, "Conversación reabierta")

    (activity, _) = (await world.use_case.execute(1)).items

    assert activity.direction is MessageDirection.ACTIVITY
    assert activity.author_type is None
    assert activity.delivery_status is None


async def test_unknown_conversation_is_not_found() -> None:
    with pytest.raises(ResourceNotFoundError):
        await _World().use_case.execute(404)
