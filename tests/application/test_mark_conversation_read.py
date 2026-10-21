"""MarkConversationRead y el enriquecimiento de ``conversation.updated`` (spec 09, 6.8 y 7.2)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.dtos.conversation_event_dto import ConversationEventType
from app.application.dtos.inbox_dto import LeadStatus
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.application.use_cases.messaging.mark_conversation_read import MarkConversationRead
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.domain.entities.client import Client
from app.domain.entities.conversation_link import ConversationLink
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.events.in_memory_conversation_event_publisher import (
    InMemoryConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from tests.application.conversation_link_support import InMemoryConversationLinkRepository
from tests.application.inbox_event_support import InMemoryClients, InMemoryInbox
from tests.application.inbox_read_support import FakeInboxLookup
from tests.application.outbox_support import InMemoryOutboxStore
from tests.application.test_inbox_gateway_events import (
    CONVERSATION_ID,
    RAW_BODY,
    RECEIVED_AT,
    _Bot,
    _Gateway,
    _incoming,
)

PHONE = PhoneNumber("+51999888777")
NOW = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)


def _read_world(
    *, publish_error: Exception | None = None
) -> tuple[MarkConversationRead, FakeMessagingAdapter, InMemoryConversationEventPublisher]:
    messaging = FakeMessagingAdapter()
    messaging.receive_text(PHONE, "Hola", name="Carlos")
    publisher = InMemoryConversationEventPublisher(error=publish_error)
    views = ConversationViewBuilder(InMemoryConversationLinkRepository(), FakeInboxLookup())
    return MarkConversationRead(messaging, views, publisher), messaging, publisher


async def test_it_resets_the_counter_and_publishes_the_full_item() -> None:
    use_case, messaging, publisher = _read_world()

    await use_case.execute(1)

    assert (await messaging.get_conversation(1)).unread_count == 0
    (event,) = publisher.events
    assert event.event is ConversationEventType.CONVERSATION_UPDATED
    assert event.data["unread_count"] == 0
    assert event.data["lead_status"] == "QUOTING"
    assert event.data["client"]["name"] == "Carlos"


async def test_a_publish_failure_never_fails_the_command() -> None:
    use_case, messaging, _ = _read_world(publish_error=ConnectionError("redis"))

    await use_case.execute(1)

    assert (await messaging.get_conversation(1)).unread_count == 0


async def test_gateway_errors_propagate_before_publishing() -> None:
    use_case, messaging, publisher = _read_world()

    with pytest.raises(ResourceNotFoundError):
        await use_case.execute(99)
    messaging.unavailable = True
    with pytest.raises(MessagingUnavailableError):
        await use_case.execute(1)
    assert publisher.events == []


# --- Enriquecimiento del worker -------------------------------------------------------------


def _worker(
    lookup: FakeInboxLookup,
    link: ConversationLink,
) -> tuple[ProcessGatewayEvent, InMemoryConversationEventPublisher]:
    store = InMemoryOutboxStore()
    links = InMemoryConversationLinkRepository()
    links.put(link)
    publisher = InMemoryConversationEventPublisher()
    use_case = ProcessGatewayEvent(
        transaction=lambda: store.transaction(),
        gateway=_Gateway(_incoming()),
        incoming_handler=_Bot(),
        inbox=InMemoryInbox(
            store, links=links, clients=InMemoryClients(Client(phone=PHONE, full_name="X"))
        ),
        publisher=publisher,
        lookup=lookup,
    )
    return use_case, publisher


def _link(**fields: object) -> ConversationLink:
    link = ConversationLink.create(chatwoot_conversation_id=CONVERSATION_ID, now=NOW)
    for key, value in fields.items():
        setattr(link, key, value)
    return link


async def test_conversation_updated_carries_lead_quote_and_assignee() -> None:
    quote_id, maria = uuid4(), uuid4()
    lookup = FakeInboxLookup(
        users={maria: "María Torres"}, quotes={quote_id: QuoteStatus.CONVERTED}
    )
    use_case, publisher = _worker(lookup, _link(quote_id=quote_id, assigned_user_id=maria))

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    updated = publisher.events[-1].data
    assert updated["quote_status"] == "CONVERTED"
    assert updated["lead_status"] == LeadStatus.CONVERTED.value
    assert updated["assigned_user_name"] == "María Torres"
    # Una pasada para decidir el reinicio del ciclo (D25) y otra para enriquecer el evento.
    assert lookup.calls == [
        "quote_statuses",
        "settled_quote_ids",
        "quote_statuses",
        "settled_quote_ids",
        "user_names",
    ]


async def test_a_lookup_failure_publishes_the_event_without_enrichment() -> None:
    lookup = FakeInboxLookup(quotes={})
    lookup.error = ConnectionError("db")
    use_case, publisher = _worker(lookup, _link(quote_id=uuid4()))

    await use_case.execute(raw_body=RAW_BODY, received_at=RECEIVED_AT)

    updated = publisher.events[-1].data
    assert "lead_status" not in updated
    assert updated["chatwoot_conversation_id"] == CONVERSATION_ID
