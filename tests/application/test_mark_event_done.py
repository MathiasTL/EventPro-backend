"""EVENT_DONE calculado y marca manual (spec 09, 4.2, 7.4, D25)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.dtos.inbox_dto import ConversationView, LeadStatus
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.application.use_cases.messaging.mark_event_done import MarkEventDone
from app.domain.entities.conversation_link import ConversationLink
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.messaging_exceptions import InvalidLeadTransitionError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.events.in_memory_conversation_event_publisher import (
    InMemoryConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from tests.application.conversation_link_support import InMemoryConversationLinkRepository
from tests.application.inbox_read_support import FakeInboxLookup
from tests.application.outbox_support import FixedClock

NOW = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
PHONE = PhoneNumber("+51999888777")
USER = uuid4()


class _World:
    def __init__(self, quote_status: QuoteStatus | None, *, settled: bool = False) -> None:
        self.quote_id = uuid4()
        self.messaging = FakeMessagingAdapter()
        self.messaging.receive_text(PHONE, "Hola", name="Carlos")
        self.conversation_id = 1
        self.links = InMemoryConversationLinkRepository()
        self.lookup = FakeInboxLookup(
            quotes={self.quote_id: quote_status} if quote_status else {},
            settled=[self.quote_id] if settled else (),
        )
        self.views = ConversationViewBuilder(self.links, self.lookup)
        self.publisher = InMemoryConversationEventPublisher()
        self.use_case = MarkEventDone(
            self.messaging, self.links, self.views, self.publisher, FixedClock(NOW)
        )
        if quote_status is not None:
            link = ConversationLink.create(chatwoot_conversation_id=self.conversation_id, now=NOW)
            link.link_quote(self.quote_id, at=NOW)
            self.links.put(link)

    async def mark(self) -> ConversationView:
        return await self.use_case.execute(self.conversation_id, user_id=USER)

    def stored(self) -> ConversationLink:
        return self.links.links[self.conversation_id]


async def test_a_converted_conversation_is_marked_and_published() -> None:
    world = _World(QuoteStatus.CONVERTED)

    view = await world.mark()

    assert view.lead_status is LeadStatus.EVENT_DONE
    assert view.quote_status is QuoteStatus.CONVERTED
    link = world.stored()
    assert (link.event_done_at, link.event_done_by_user_id) == (NOW, USER)
    assert link.quote_id == world.quote_id
    assert [e.data["lead_status"] for e in world.publisher.events] == ["EVENT_DONE"]


@pytest.mark.parametrize(
    "quote_status",
    [
        None,
        QuoteStatus.SENT,
        QuoteStatus.PAYMENT_STARTED,
        QuoteStatus.EXPIRED,
        QuoteStatus.CANCELLED,
    ],
)
async def test_any_other_lead_status_is_rejected_without_writing(
    quote_status: QuoteStatus | None,
) -> None:
    world = _World(quote_status)

    with pytest.raises(InvalidLeadTransitionError):
        await world.mark()

    assert world.publisher.events == []
    link = world.links.links.get(world.conversation_id)
    assert link is None or link.event_done_at is None


async def test_marking_twice_is_idempotent() -> None:
    world = _World(QuoteStatus.CONVERTED)
    await world.mark()
    first = world.stored().event_done_at

    view = await world.mark()

    assert view.lead_status is LeadStatus.EVENT_DONE
    assert world.stored().event_done_at == first
    assert len(world.publisher.events) == 1


async def test_a_settled_event_is_already_event_done_without_any_mark() -> None:
    world = _World(QuoteStatus.CONVERTED, settled=True)

    view = await world.mark()

    assert view.lead_status is LeadStatus.EVENT_DONE
    assert world.stored().event_done_at is None
    assert world.publisher.events == []


async def test_a_publish_failure_never_fails_the_mark() -> None:
    world = _World(QuoteStatus.CONVERTED)
    world.publisher.error = RuntimeError("redis caído")

    view = await world.mark()

    assert view.lead_status is LeadStatus.EVENT_DONE
    assert world.stored().event_done_at == NOW


async def test_gateway_errors_propagate() -> None:
    world = _World(QuoteStatus.CONVERTED)
    with pytest.raises(ResourceNotFoundError):
        await world.use_case.execute(999, user_id=USER)


async def test_views_derive_event_done_in_one_batch_for_every_conversation() -> None:
    world = _World(QuoteStatus.CONVERTED, settled=True)
    world.messaging.receive_text(PhoneNumber("+51911222333"), "Hola", name="Ana")
    other_id = 2
    manual_quote: UUID = uuid4()
    world.lookup.quotes[manual_quote] = QuoteStatus.CONVERTED
    link = ConversationLink.create(chatwoot_conversation_id=other_id, now=NOW)
    link.link_quote(manual_quote, at=NOW)
    link.mark_event_done(user_id=USER, at=NOW)
    world.links.put(link)
    summaries = [
        await world.messaging.get_conversation(world.conversation_id),
        await world.messaging.get_conversation(other_id),
    ]
    world.lookup.calls.clear()

    views = await world.views.build(summaries)

    assert [v.lead_status for v in views] == [LeadStatus.EVENT_DONE, LeadStatus.EVENT_DONE]
    assert world.lookup.calls.count("settled_quote_ids") == 1
