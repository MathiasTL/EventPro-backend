"""ListConversations y GetConversation: unión con vínculos, filtros y búsqueda (spec 09, 4.1)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.dtos.inbox_dto import (
    AssignedFilter,
    ConversationFilters,
    ConversationView,
    LeadStatus,
)
from app.application.dtos.messaging_dto import ConversationLifecycle, ConversationStatus
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.application.use_cases.messaging.list_conversations import (
    GetConversation,
    ListConversations,
)
from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from tests.application.conversation_link_support import InMemoryConversationLinkRepository
from tests.application.inbox_read_support import FakeInboxLookup

NOW = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)
ME = uuid4()
MARIA = uuid4()
CARLOS_ID = uuid4()
BOT_PHONE = PhoneNumber("+51911111111")
CARLOS_PHONE = PhoneNumber("+51999888777")
ANA_PHONE = PhoneNumber("+51922333444")
OLD_PHONE = PhoneNumber("+51955000111")
QUOTE_ID = uuid4()


class _CountingLinks(InMemoryConversationLinkRepository):
    def __init__(self) -> None:
        super().__init__()
        self.batch_reads = 0

    async def get_many(self, conversation_ids):  # type: ignore[no-untyped-def]
        self.batch_reads += 1
        return await super().get_many(conversation_ids)


class _World:
    """Cuatro conversaciones: bot, Carlos (humano, de María), Ana (humano sin asignar), vieja."""

    def __init__(self) -> None:
        self.messaging = FakeMessagingAdapter()
        self.links = _CountingLinks()
        self.lookup = FakeInboxLookup(
            clients={CARLOS_ID: "Carlos Ramírez"},
            users={MARIA: "María Torres", ME: "Yo Mismo"},
            quotes={QUOTE_ID: QuoteStatus.SENT},
        )
        self.messaging.receive_text(OLD_PHONE, "Hola", name="Vieja Resuelta")
        self.messaging.receive_text(ANA_PHONE, "Buenas", name="Ana Pérez")
        self.messaging.receive_text(CARLOS_PHONE, "Cotización", name="Perfil WA")
        self.messaging.receive_text(BOT_PHONE, "Hola bot", name="Luis Bot")
        self.ids = {
            "old": 1,
            "ana": 2,
            "carlos": 3,
            "bot": 4,
        }
        self.messaging.resolve_conversation(self.ids["old"])
        for name in ("ana", "carlos"):
            self.messaging._conversations[self.ids[name]].status = ConversationStatus.HUMAN
        self._link("carlos", client_id=CARLOS_ID, quote_id=QUOTE_ID, assigned=MARIA)
        self._link("ana", assigned=None)
        self.links.links[self.ids["old"]] = self._make_link("old", assigned=MARIA)
        builder = ConversationViewBuilder(self.links, self.lookup)
        self.list = ListConversations(self.messaging, builder)
        self.get = GetConversation(self.messaging, builder)

    def _make_link(self, name: str, **fields: object) -> ConversationLink:
        link = ConversationLink.create(chatwoot_conversation_id=self.ids[name], now=NOW)
        link.assigned_user_id = fields.pop("assigned", None)  # type: ignore[assignment]
        for key, value in fields.items():
            setattr(link, key, value)
        return link

    def _link(self, name: str, **fields: object) -> None:
        link = self._make_link(name, **fields)
        link.last_client_message_at = NOW
        link.register_handoff(reason=HandoffReason.CLIENT_REQUEST, summary=None, at=NOW)
        self.links.put(link)

    async def run(self, user_id: UUID = ME, **filters: object) -> list[ConversationView]:
        page = await self.list.execute(ConversationFilters(**filters), user_id=user_id)  # type: ignore[arg-type]
        return list(page.items)


async def _names(world: _World, **filters: object) -> list[str]:
    return [view.client_name for view in await world.run(**filters)]


async def test_it_merges_chatwoot_links_and_batch_lookups() -> None:
    world = _World()

    views = {v.chatwoot_conversation_id: v for v in await world.run()}

    carlos = views[world.ids["carlos"]]
    assert carlos.client_id == CARLOS_ID
    assert carlos.client_name == "Carlos Ramírez"
    assert carlos.mode is ConversationStatus.HUMAN
    assert carlos.assigned_user_id == MARIA
    assert carlos.assigned_user_name == "María Torres"
    assert carlos.quote_status is QuoteStatus.SENT
    assert carlos.lead_status is LeadStatus.QUOTE_SENT
    assert carlos.handoff_reason is HandoffReason.CLIENT_REQUEST
    assert carlos.service_window_expires_at == NOW + timedelta(hours=24)
    # Sin cliente registrado, el nombre cae al contacto de Chatwoot.
    assert views[world.ids["ana"]].client_name == "Ana Pérez"
    # Sin vínculo, todo cae a los valores por defecto.
    bot = views[world.ids["bot"]]
    assert (bot.client_id, bot.lead_status, bot.service_window_expires_at) == (
        None,
        LeadStatus.QUOTING,
        None,
    )


async def test_it_reads_each_batch_once_per_page() -> None:
    world = _World()

    await world.run()

    assert world.links.batch_reads == 1
    assert sorted(world.lookup.calls) == ["client_names", "quote_statuses", "user_names"]


async def test_it_hides_resolved_conversations_unless_requested() -> None:
    world = _World()

    assert "Vieja Resuelta" not in await _names(world)
    assert "Vieja Resuelta" in await _names(world, include_resolved=True)


async def test_resolved_conversations_report_no_assignee() -> None:
    world = _World()

    (old,) = [
        v for v in await world.run(include_resolved=True) if v.client_name == "Vieja Resuelta"
    ]

    assert old.lifecycle is ConversationLifecycle.RESOLVED
    assert old.assigned_user_id is None
    assert old.mode is ConversationStatus.BOT


async def test_it_sorts_by_last_message_descending() -> None:
    world = _World()

    assert await _names(world) == ["Luis Bot", "Carlos Ramírez", "Ana Pérez"]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"mode": ConversationStatus.BOT}, ["Luis Bot"]),
        ({"mode": ConversationStatus.HUMAN}, ["Carlos Ramírez", "Ana Pérez"]),
        ({"assigned": AssignedFilter.UNASSIGNED}, ["Ana Pérez"]),
        ({"assigned": AssignedFilter.ME}, []),
        ({"assigned_user_id": MARIA}, ["Carlos Ramírez"]),
        ({"mode": ConversationStatus.HUMAN, "assigned_user_id": MARIA}, ["Carlos Ramírez"]),
    ],
)
async def test_it_filters_by_mode_and_assignment(
    filters: dict[str, object], expected: list[str]
) -> None:
    assert await _names(_World(), **filters) == expected


async def test_assigned_me_matches_the_calling_user() -> None:
    world = _World()

    assert await _names(world, user_id=MARIA, assigned=AssignedFilter.ME) == ["Carlos Ramírez"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("carlos", ["Carlos Ramírez"]),
        ("RAMIREZ", ["Carlos Ramírez"]),  # sin distinguir mayúsculas ni tildes
        ("pérez", ["Ana Pérez"]),
        ("99 988", ["Carlos Ramírez"]),  # dígitos del teléfono
        ("+51922", ["Ana Pérez"]),
        ("zz", []),
    ],
)
async def test_it_searches_by_name_and_phone_digits(query: str, expected: list[str]) -> None:
    assert await _names(_World(), q=query) == expected


async def test_it_paginates_after_filtering() -> None:
    world = _World()

    page = await world.list.execute(ConversationFilters(page=2, page_size=2), user_id=ME)

    assert (page.total, page.page, page.page_size) == (3, 2, 2)
    assert [v.client_name for v in page.items] == ["Ana Pérez"]


async def test_get_conversation_returns_the_same_item_and_includes_resolved() -> None:
    world = _World()

    carlos = await world.get.execute(world.ids["carlos"])
    old = await world.get.execute(world.ids["old"])

    assert carlos.client_name == "Carlos Ramírez"
    assert old.lifecycle is ConversationLifecycle.RESOLVED


async def test_get_conversation_raises_not_found() -> None:
    with pytest.raises(ResourceNotFoundError):
        await _World().get.execute(999)


async def test_gateway_failure_propagates() -> None:
    world = _World()
    world.messaging.unavailable = True

    with pytest.raises(MessagingUnavailableError):
        await world.run()
