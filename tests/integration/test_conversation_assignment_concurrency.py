"""Takeover concurrente sobre PostgreSQL 16 real (spec 09, 6.3, D11)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.application.dtos.messaging_dto import ConversationSummary
from app.application.services.audit_service import AuditService
from app.application.use_cases.messaging.conversation_assignment import TakeoverConversation
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.domain.exceptions.messaging_exceptions import ConversationTakenByOtherError
from app.domain.value_objects.phone_number import PhoneNumber
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.cache.in_memory_conversation_session_adapter import (
    InMemoryConversationSessionAdapter,
)
from app.infrastructure.adapters.secondary.events.in_memory_conversation_event_publisher import (
    InMemoryConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_conversation_link_repository import (  # noqa: E501
    SqlAlchemyConversationLinkRepository,
)
from app.infrastructure.adapters.secondary.persistence.sqlalchemy_conversation_link_unit_of_work import (  # noqa: E501
    SqlAlchemyConversationLinkUnitOfWork,
)
from tests.application.assignment_support import InMemoryAuditPort
from tests.application.inbox_read_support import FakeInboxLookup
from tests.application.outbox_support import FixedClock

from ._support import insert_user, run_migrations

pytestmark = pytest.mark.integration

PHONE = PhoneNumber("+51999888777")


class _OverlappingMessaging(FakeMessagingAdapter):
    """Ambos takeovers leen la conversación antes de que cualquiera llegue a reclamarla."""

    def __init__(self) -> None:
        super().__init__()
        self.arrivals = asyncio.Barrier(2)

    async def get_conversation(self, conversation_id: int) -> ConversationSummary:
        summary = await super().get_conversation(conversation_id)
        await asyncio.wait_for(self.arrivals.wait(), timeout=10)
        return summary


@pytest.fixture(scope="module")
def migrated_url(database_url: str) -> str:
    run_migrations(database_url)
    return database_url


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(migrated_url)
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM conversation_links"))
    yield engine
    await engine.dispose()


async def test_two_concurrent_takeovers_have_exactly_one_winner(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    messaging = _OverlappingMessaging()
    messaging.receive_text(PHONE, "Hola", name="Carlos")
    first = await insert_user(engine, "ENCARGADO")
    second = await insert_user(engine, "ENCARGADO")
    publisher = InMemoryConversationEventPublisher()

    def use_case() -> TakeoverConversation:
        # Cada petición real tiene su propia sesión de lectura y su propia unidad de trabajo.
        reads = factory()
        views = ConversationViewBuilder(
            SqlAlchemyConversationLinkRepository(reads), FakeInboxLookup()
        )
        return TakeoverConversation(
            messaging,
            SqlAlchemyConversationLinkUnitOfWork(factory),
            views,
            InMemoryConversationSessionAdapter(),
            AuditService(InMemoryAuditPort()),
            publisher,
            FixedClock(datetime(2026, 10, 20, 15, 0, tzinfo=UTC)),
        )

    outcomes = await asyncio.gather(
        use_case().execute(1, user_id=first, role=Role.ENCARGADO),
        use_case().execute(1, user_id=second, role=Role.ENCARGADO),
        return_exceptions=True,
    )

    winners = [o for o in outcomes if not isinstance(o, BaseException)]
    losers = [o for o in outcomes if isinstance(o, BaseException)]
    assert len(winners) == 1
    assert len(losers) == 1 and isinstance(losers[0], ConversationTakenByOtherError)
    winner_id = winners[0].assigned_user_id
    assert winner_id in (first, second)
    assert losers[0].assigned_user_id == winner_id
    async with factory() as session:
        link = await SqlAlchemyConversationLinkRepository(session).get(1)
    assert link is not None and link.assigned_user_id == winner_id
    assert len(publisher.events) == 1
