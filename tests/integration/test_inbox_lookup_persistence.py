"""Consultas por lote de la bandeja y búsquedas del outbox con PostgreSQL 16 (spec 09, 5.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.entities.quote import QuoteStatus
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_inbox_lookup import (
    SqlAlchemyInboxLookup,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxRepository,
)
from tests.domain.outbox_support import NOW, make_message

from ._support import insert_quotes, insert_user, run_migrations

pytestmark = pytest.mark.integration

PHONE = PhoneNumber("+51999777555")


@pytest.fixture(scope="module")
def migrated_url(database_url: str) -> str:
    run_migrations(database_url)
    return database_url


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(migrated_url)
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM outbox_messages"))
    yield engine
    await engine.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_lookup_resolves_names_and_quote_status_in_batches(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    user_id = await insert_user(engine, "ENCARGADO")
    quote_id = uuid4()
    await insert_quotes(engine, [quote_id])
    async with engine.begin() as connection:
        client_id = await connection.scalar(
            text("SELECT client_id FROM quotes WHERE id = :id"), {"id": quote_id}
        )
    lookup = SqlAlchemyInboxLookup(factory)

    assert await lookup.user_names([user_id, uuid4()]) == {user_id: "Usuario de prueba"}
    assert await lookup.client_names([client_id]) == {client_id: "Cliente de prueba"}
    assert await lookup.quote_statuses([quote_id, uuid4()]) == {quote_id: QuoteStatus.SENT}
    assert await lookup.user_names([]) == {}


async def test_settled_quote_ids_only_returns_quotes_whose_event_is_settled(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    settled, scheduled, without_event = uuid4(), uuid4(), uuid4()
    await insert_quotes(engine, [settled, scheduled, without_event])
    async with engine.begin() as connection:
        for quote_id, status in ((settled, "SETTLED"), (scheduled, "SCHEDULED")):
            await connection.execute(
                text(
                    "INSERT INTO events (event_code, quote_id, event_date, start_time, "
                    "end_time, address, district, total_services_amount, "
                    "total_mobility_amount, final_total_amount, status) "
                    "VALUES (:code, :quote_id, '2026-10-15', '21:30', '22:30', "
                    "'Av. Benavides', 'Miraflores', 980, 100, 1080, :status)"
                ),
                {"code": f"EVT-{quote_id.hex[:8]}", "quote_id": quote_id, "status": status},
            )
    lookup = SqlAlchemyInboxLookup(factory)

    found = await lookup.settled_quote_ids([settled, scheduled, without_event, uuid4()])

    assert found == {settled}
    assert await lookup.settled_quote_ids([]) == set()


async def test_outbox_batch_lookup_matches_current_and_retried_ids(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    current = make_message(recipient=PHONE)
    current.mark_sent(external_message_id="d1", conversation_id=1, now=NOW)
    retried = make_message(recipient=PHONE)
    retried.mark_sent(external_message_id="d2", conversation_id=1, now=NOW)
    retried.retried_external_message_id = "d2-old"
    async with factory() as session, session.begin():
        repo = SqlAlchemyOutboxRepository(session)
        await repo.add(current)
        await repo.add(retried)
    async with factory() as session:
        found = await SqlAlchemyOutboxRepository(session).get_many_by_external_ids(
            {"d1", "d2-old", "missing"}
        )

    assert {key: row.id for key, row in found.items()} == {
        "d1": current.id,
        "d2-old": retried.id,
    }


async def test_unsent_for_recipient_lists_pending_and_failed_only(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    pending = make_message(recipient=PHONE)
    failed = make_message(recipient=PHONE)
    failed.register_failure(error="Boom", permanent=True, now=NOW)
    sent = make_message(recipient=PHONE)
    sent.mark_sent(external_message_id="s1", conversation_id=1, now=NOW)
    other = make_message(recipient=PhoneNumber("+51900000001"))
    async with factory() as session, session.begin():
        repo = SqlAlchemyOutboxRepository(session)
        for row in (pending, failed, sent, other):
            await repo.add(row)
    async with factory() as session:
        rows = await SqlAlchemyOutboxRepository(session).list_unsent_for_recipient(PHONE)

    assert {row.id for row in rows} == {pending.id, failed.id}
