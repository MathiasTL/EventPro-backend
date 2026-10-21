"""conversation_links sobre PostgreSQL 16 real: ensure, claim y release (D1, D11)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.models import Base
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_conversation_link_repository import (  # noqa: E501
    SqlAlchemyConversationLinkRepository,
)

from ._support import insert_user, run_migrations

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
CONVERSATION = 4101


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


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _ensure(
    factory: async_sessionmaker[AsyncSession], conversation_id: int = CONVERSATION
) -> ConversationLink:
    async with factory() as session, session.begin():
        return await SqlAlchemyConversationLinkRepository(session).ensure(
            conversation_id, None, NOW
        )


async def _claim(
    factory: async_sessionmaker[AsyncSession],
    user_id: UUID,
    expected: UUID | None,
    conversation_id: int = CONVERSATION,
) -> bool:
    async with factory() as session, session.begin():
        return await SqlAlchemyConversationLinkRepository(session).claim(
            conversation_id, user_id, expected
        )


async def _release(
    factory: async_sessionmaker[AsyncSession],
    expected: UUID,
    conversation_id: int = CONVERSATION,
) -> bool:
    async with factory() as session, session.begin():
        return await SqlAlchemyConversationLinkRepository(session).release(
            conversation_id, expected
        )


async def _assignee(factory: async_sessionmaker[AsyncSession]) -> UUID | None:
    async with factory() as session:
        link = await SqlAlchemyConversationLinkRepository(session).get(CONVERSATION)
    assert link is not None
    return link.assigned_user_id


# --- ensure (STRICT) ----------------------------------------------------------------------


async def test_ensure_creates_an_unassigned_link_without_client(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    link = await _ensure(factory)

    assert link.chatwoot_conversation_id == CONVERSATION
    assert link.client_id is None
    assert link.assigned_user_id is None
    assert link.created_at == NOW
    assert link.last_client_message_at is None


async def test_ensure_is_idempotent_and_keeps_the_first_row(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await _ensure(factory)
    second = await _ensure(factory)

    assert second.id == first.id


async def test_two_concurrent_ensure_calls_leave_a_single_row(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    results = await asyncio.gather(*(_ensure(factory) for _ in range(2)))

    assert results[0].id == results[1].id
    async with engine.connect() as connection:
        count = await connection.scalar(text("SELECT count(*) FROM conversation_links"))
    assert count == 1


# --- claim (STRICT) -----------------------------------------------------------------------


async def test_claim_of_an_unassigned_link_wins_and_records_the_assignee(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    user = await insert_user(engine, "ENCARGADO")

    assert await _claim(factory, user, None) is True
    assert await _assignee(factory) == user


async def test_claim_with_a_stale_expected_assignee_loses_and_changes_nothing(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    first = await insert_user(engine, "ENCARGADO")
    second = await insert_user(engine, "ENCARGADO")
    await _claim(factory, first, None)

    assert await _claim(factory, second, None) is False
    assert await _assignee(factory) == first


async def test_claim_reassigns_when_the_expected_assignee_matches(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    first = await insert_user(engine, "ENCARGADO")
    admin = await insert_user(engine, "SUPERADMIN")
    await _claim(factory, first, None)

    assert await _claim(factory, admin, first) is True
    assert await _assignee(factory) == admin


async def test_claim_of_a_missing_link_loses(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    user = await insert_user(engine, "ENCARGADO")

    assert await _claim(factory, user, None, conversation_id=999) is False


async def test_two_concurrent_claims_on_an_unassigned_link_have_exactly_one_winner(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    first = await insert_user(engine, "ENCARGADO")
    second = await insert_user(engine, "ENCARGADO")

    outcomes = await asyncio.gather(_claim(factory, first, None), _claim(factory, second, None))

    assert sorted(outcomes) == [False, True]
    assert await _assignee(factory) == (first if outcomes[0] else second)


# --- release (STRICT) ---------------------------------------------------------------------


async def test_release_by_the_expected_assignee_clears_the_assignment(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    user = await insert_user(engine, "ENCARGADO")
    await _claim(factory, user, None)

    assert await _release(factory, user) is True
    assert await _assignee(factory) is None


async def test_release_with_a_different_expected_assignee_loses(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    owner = await insert_user(engine, "ENCARGADO")
    other = await insert_user(engine, "ENCARGADO")
    await _claim(factory, owner, None)

    assert await _release(factory, other) is False
    assert await _assignee(factory) == owner


async def test_release_of_an_unassigned_link_loses(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    user = await insert_user(engine, "ENCARGADO")

    assert await _release(factory, user) is False


async def test_claim_and_release_race_never_leaves_two_owners(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    await _ensure(factory)
    owner = await insert_user(engine, "ENCARGADO")
    rival = await insert_user(engine, "ENCARGADO")
    await _claim(factory, owner, None)

    released, claimed = await asyncio.gather(
        _release(factory, owner), _claim(factory, rival, owner)
    )

    assert released is True or claimed is True
    final = await _assignee(factory)
    assert final == (rival if claimed else None)


# --- resto (RELAXED) ----------------------------------------------------------------------


async def test_get_many_returns_only_existing_links(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await _ensure(factory, 1)
    await _ensure(factory, 2)

    async with factory() as session:
        repository = SqlAlchemyConversationLinkRepository(session)
        found = await repository.get_many([1, 2, 3])
        assert await repository.get_many([]) == []
    assert sorted(link.chatwoot_conversation_id for link in found) == [1, 2]


async def test_save_round_trips_every_field_and_keeps_the_assignment(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    link = await _ensure(factory)
    user = await insert_user(engine, "ENCARGADO")
    marker = await insert_user(engine, "SUPERADMIN")
    await _claim(factory, user, None)
    later = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
    link.register_handoff(reason=HandoffReason.CLIENT_REQUEST, summary="Quiere un DJ", at=later)
    link.record_client_message(later)
    link.mark_event_done(user_id=marker, at=later)
    link.restart_lead_cycle(at=later)
    link.mark_event_done(user_id=marker, at=later)

    async with factory() as session, session.begin():
        await SqlAlchemyConversationLinkRepository(session).save(link)

    async with factory() as session:
        stored = await SqlAlchemyConversationLinkRepository(session).get(CONVERSATION)
    assert stored is not None
    assert stored.handoff_reason is HandoffReason.CLIENT_REQUEST
    assert stored.handoff_summary == "Quiere un DJ"
    assert stored.handed_off_at == later
    assert stored.last_client_message_at == later
    assert stored.event_done_at == later
    assert stored.event_done_by_user_id == marker
    assert stored.lead_cycle_started_at == later
    assert stored.updated_at == later
    assert stored.assigned_user_id == user  # el guardado con datos viejos no pisa la toma


async def test_save_of_a_missing_link_raises_not_found(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    ghost = ConversationLink.create(chatwoot_conversation_id=77, now=NOW)

    async with factory() as session, session.begin():
        with pytest.raises(ResourceNotFoundError):
            await SqlAlchemyConversationLinkRepository(session).save(ghost)


async def test_link_may_reference_a_registered_client(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    async with engine.begin() as connection:
        client_id = await connection.scalar(
            text(
                "INSERT INTO clients (phone, full_name) "
                f"VALUES ('+51{uuid4().int % 10**9:09d}', 'Ana') RETURNING id"
            )
        )
    async with factory() as session, session.begin():
        link = await SqlAlchemyConversationLinkRepository(session).ensure(5, client_id, NOW)
    assert link.client_id == client_id


async def test_orm_models_match_the_alembic_schema(engine: AsyncEngine) -> None:
    def in_scope(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object):
        table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
        return table in {"conversation_links", "outbox_messages"}

    def diff(connection) -> list[object]:  # type: ignore[no-untyped-def]
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": in_scope,
            },
        )
        return compare_metadata(context, Base.metadata)

    async with engine.connect() as connection:
        differences = await connection.run_sync(diff)
    assert differences == []
