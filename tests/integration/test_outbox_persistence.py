"""Outbox sobre PostgreSQL 16 real: persistencia, reserva concurrente y transacciones."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.use_cases.messaging.dispatch_due_messages import DispatchDueMessages
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.outbox import DeliveryStatus, MessageType, OutboxStatus
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.models import Base
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxRepository,
    SqlAlchemyOutboxTransaction,
)
from tests.application.outbox_support import FakeDocumentSource, FixedClock
from tests.domain.outbox_support import (
    DOCUMENT_PAYLOAD,
    INTERACTIVE_PAYLOAD,
    NOW,
    PHONE,
    TEMPLATE_PAYLOAD,
    TEXT_PAYLOAD,
    make_message,
)

from ._support import insert_user, run_migrations

pytestmark = pytest.mark.integration

LEASE = timedelta(seconds=60)


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


async def _add_all(
    factory: async_sessionmaker[AsyncSession], messages: list[OutboxMessage]
) -> list[OutboxMessage]:
    async with factory() as session, session.begin():
        repository = SqlAlchemyOutboxRepository(session)
        for message in messages:
            await repository.add(message)
    return messages


async def _reload(factory: async_sessionmaker[AsyncSession], message: OutboxMessage) -> Any:
    async with factory() as session:
        return await SqlAlchemyOutboxRepository(session).get_by_id(message.id)


def _due(count: int, *, minutes_apart: int = 1) -> list[OutboxMessage]:
    return [
        make_message(
            payload={"body": f"mensaje {index}"}, now=NOW - timedelta(minutes=index * minutes_apart)
        )
        for index in range(count)
    ]


# --- persistencia ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message_type", "payload"),
    [
        (MessageType.TEXT, TEXT_PAYLOAD),
        (MessageType.TEMPLATE, TEMPLATE_PAYLOAD),
        (MessageType.INTERACTIVE, INTERACTIVE_PAYLOAD),
        (MessageType.DOCUMENT, DOCUMENT_PAYLOAD),
    ],
)
async def test_round_trip_preserves_every_field_for_each_message_type(
    factory: async_sessionmaker[AsyncSession],
    message_type: MessageType,
    payload: dict[str, Any],
) -> None:
    message = make_message(message_type=message_type, payload=payload, redact_after_send=True)
    message.register_failure(error="caído", permanent=False, now=NOW)
    await _add_all(factory, [message])

    assert await _reload(factory, message) == message


async def test_sent_and_delivered_state_round_trips(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    message = make_message()
    message.mark_sent(external_message_id="cw-1", conversation_id=77, now=NOW)
    message.record_delivery(status=DeliveryStatus.READ, error=None, at=NOW + timedelta(minutes=1))
    await _add_all(factory, [message])

    loaded = await _reload(factory, message)

    assert loaded == message
    assert loaded.status is OutboxStatus.SENT
    assert loaded.delivery_status is DeliveryStatus.READ
    assert loaded.conversation_id == 77


async def test_author_and_retried_external_id_round_trip(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    author = await insert_user(engine, "ENCARGADO")
    message = make_message(author_user_id=author)
    await _add_all(factory, [message])
    assert (await _reload(factory, message)).author_user_id == author

    message.retried_external_message_id = "cw-old"
    async with factory() as session, session.begin():
        await SqlAlchemyOutboxRepository(session).save(message)

    loaded = await _reload(factory, message)
    assert loaded == message
    assert loaded.author_user_id == author
    assert loaded.retried_external_message_id == "cw-old"


async def test_bot_messages_have_no_author(factory: async_sessionmaker[AsyncSession]) -> None:
    message = make_message()
    await _add_all(factory, [message])

    loaded = await _reload(factory, message)

    assert loaded.author_user_id is None
    assert loaded.retried_external_message_id is None


async def test_redacted_payload_is_stored_as_sql_null(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    message = make_message(redact_after_send=True)
    await _add_all(factory, [message])
    message.mark_sent(external_message_id="cw-otp", conversation_id=1, now=NOW)
    async with factory() as session, session.begin():
        await SqlAlchemyOutboxRepository(session).save(message)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT payload IS NULL AS is_null, redact_after_send FROM outbox_messages")
            )
        ).one()
    assert tuple(row) == (True, True)
    assert (await _reload(factory, message)).payload is None


async def test_save_of_a_missing_message_raises_not_found(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        with pytest.raises(ResourceNotFoundError):
            await SqlAlchemyOutboxRepository(session).save(make_message())


async def test_lookup_by_external_id_and_unique_constraint(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    first, second = make_message(), make_message()
    first.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    second.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    await _add_all(factory, [first])

    async with factory() as session:
        repository = SqlAlchemyOutboxRepository(session)
        found = await repository.get_by_external_id("cw-1")
        assert found is not None and found.id == first.id
        assert await repository.get_by_external_id("desconocido") is None

    with pytest.raises(IntegrityError):
        await _add_all(factory, [second])


async def test_get_by_id_for_update_blocks_a_concurrent_writer_until_commit(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    (message,) = await _add_all(factory, [make_message()])

    async with factory() as holder, holder.begin():
        await SqlAlchemyOutboxRepository(holder).get_by_id(message.id, for_update=True)

        async def competitor() -> bool:
            async with factory() as session, session.begin():
                found = await SqlAlchemyOutboxRepository(session).get_by_id(
                    message.id, for_update=True
                )
                return found is not None

        task = asyncio.create_task(competitor())
        done, _ = await asyncio.wait({task}, timeout=0.5)
        assert not done  # la segunda lectura espera mientras la primera no confirme
    assert await asyncio.wait_for(task, timeout=5) is True


# --- reserva (claim_due) ---------------------------------------------------------------


async def test_claim_due_returns_only_due_pending_messages_oldest_first(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    oldest, middle, newest = _due(3, minutes_apart=10)[::-1]
    future = make_message(now=NOW + timedelta(minutes=5))
    sent = make_message()
    sent.mark_sent(external_message_id="cw-1", conversation_id=1, now=NOW)
    failed = make_message()
    failed.register_failure(error="x", permanent=True, now=NOW)
    await _add_all(factory, [newest, future, sent, failed, oldest, middle])

    async with factory() as session, session.begin():
        claimed = await SqlAlchemyOutboxRepository(session).claim_due(
            now=NOW, limit=10, lease=LEASE
        )

    assert [message.id for message in claimed] == [oldest.id, middle.id, newest.id]


async def test_claim_due_respects_the_limit(factory: async_sessionmaker[AsyncSession]) -> None:
    messages = await _add_all(factory, _due(5))

    async with factory() as session, session.begin():
        claimed = await SqlAlchemyOutboxRepository(session).claim_due(now=NOW, limit=2, lease=LEASE)

    assert [message.id for message in claimed] == [messages[4].id, messages[3].id]


async def test_claim_due_pushes_next_attempt_at_forward_by_the_lease(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    (message,) = await _add_all(factory, [make_message()])

    async with factory() as session, session.begin():
        (claimed,) = await SqlAlchemyOutboxRepository(session).claim_due(
            now=NOW, limit=5, lease=LEASE
        )

    assert claimed.next_attempt_at == NOW + LEASE
    assert (await _reload(factory, message)).next_attempt_at == NOW + LEASE
    assert (await _reload(factory, message)).status is OutboxStatus.PENDING


async def test_two_concurrent_sessions_never_claim_the_same_message(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    messages = await _add_all(factory, _due(6))

    async with factory() as first, first.begin(), factory() as second, second.begin():
        claimed_first = await SqlAlchemyOutboxRepository(first).claim_due(
            now=NOW, limit=3, lease=LEASE
        )
        # La primera transacción sigue abierta: SKIP LOCKED evita que la segunda espere.
        claimed_second = await asyncio.wait_for(
            SqlAlchemyOutboxRepository(second).claim_due(now=NOW, limit=3, lease=LEASE),
            timeout=5,
        )

    ids_first = {message.id for message in claimed_first}
    ids_second = {message.id for message in claimed_second}
    assert len(ids_first) == len(ids_second) == 3
    assert ids_first.isdisjoint(ids_second)
    assert ids_first | ids_second == {message.id for message in messages}


async def test_a_claimed_message_returns_only_after_the_lease_expires(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    (message,) = await _add_all(factory, [make_message()])

    async def claim(at_offset: timedelta) -> list[OutboxMessage]:
        async with factory() as session, session.begin():
            claimed = await SqlAlchemyOutboxRepository(session).claim_due(
                now=NOW + at_offset, limit=5, lease=LEASE
            )
            return list(claimed)

    assert [m.id for m in await claim(timedelta(0))] == [message.id]
    assert await claim(timedelta(seconds=1)) == []
    assert await claim(timedelta(seconds=59)) == []
    # El worker murió sin guardar el resultado: al vencer la reserva vuelve a estar disponible.
    assert [m.id for m in await claim(timedelta(seconds=61))] == [message.id]


# --- despacho completo sobre la base real ---------------------------------------------------


def _dispatcher(
    factory: async_sessionmaker[AsyncSession],
    messaging: FakeMessagingAdapter,
    *,
    batch_size: int = 20,
    documents: FakeDocumentSource | None = None,
) -> DispatchDueMessages:
    return DispatchDueMessages(
        transaction=SqlAlchemyOutboxTransaction(factory),
        messaging=messaging,
        documents=documents or FakeDocumentSource(),
        clock=FixedClock(),
        batch_size=batch_size,
        lease_seconds=60,
    )


async def test_a_dispatch_cycle_persists_each_result(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    ok = make_message(payload={"body": "uno"})
    otp = make_message(payload={"body": "código 123456"}, redact_after_send=True)
    document = make_message(message_type=MessageType.DOCUMENT)
    await _add_all(factory, [ok, otp, document])
    documents = FakeDocumentSource({"database/contracts/abc": b"%PDF-1.4"})
    messaging = FakeMessagingAdapter()

    summary = await _dispatcher(factory, messaging, documents=documents).execute()

    assert (summary.claimed, summary.sent) == (3, 3)
    assert (await _reload(factory, ok)).status is OutboxStatus.SENT
    assert (await _reload(factory, otp)).payload is None
    assert (await _reload(factory, document)).external_message_id is not None


async def test_gateway_outage_reschedules_in_the_database(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    (message,) = await _add_all(factory, [make_message()])
    messaging = FakeMessagingAdapter()
    messaging.unavailable = True

    await _dispatcher(factory, messaging).execute()

    loaded = await _reload(factory, message)
    assert loaded.status is OutboxStatus.PENDING
    assert loaded.attempts == 1
    assert loaded.next_attempt_at == NOW + timedelta(seconds=30)


async def test_two_concurrent_dispatchers_send_each_message_exactly_once(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    messages = await _add_all(factory, _due(12))
    messaging = FakeMessagingAdapter()

    first, second = await asyncio.gather(
        _dispatcher(factory, messaging, batch_size=5).execute(),
        _dispatcher(factory, messaging, batch_size=5).execute(),
    )

    assert first.claimed + second.claimed == 10  # dos lotes de 5, sin solaparse
    assert first.sent + second.sent == 10
    while (await _dispatcher(factory, messaging, batch_size=5).execute()).claimed:
        pass
    bodies = sorted(str(sent.body) for sent in messaging.sent)
    assert bodies == sorted(f"mensaje {index}" for index in range(12))  # ninguno repetido
    for message in messages:
        assert (await _reload(factory, message)).status is OutboxStatus.SENT


# --- encolado y transacción del llamador --------------------------------------------------


async def _client_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(
            await connection.scalar(
                text("SELECT count(*) FROM clients WHERE phone = '+51999777666'")
            )
            or 0
        )


async def _outbox_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(text("SELECT count(*) FROM outbox_messages")) or 0)


async def _business_operation_with_enqueue(session: AsyncSession) -> None:
    await session.execute(
        text("INSERT INTO clients (phone, full_name) VALUES ('+51999777666', 'Cliente outbox')")
    )
    await EnqueueMessage(SqlAlchemyOutboxRepository(session), FixedClock()).execute(
        recipient=PHONE, message_type=MessageType.TEXT, payload=TEXT_PAYLOAD
    )


async def test_enqueue_and_business_write_commit_together(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM clients WHERE phone = '+51999777666'"))

    async with factory() as session, session.begin():
        await _business_operation_with_enqueue(session)

    assert await _client_count(engine) == 1
    assert await _outbox_count(engine) == 1


async def test_enqueue_and_business_write_roll_back_together(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM clients WHERE phone = '+51999777666'"))

    with pytest.raises(RuntimeError):
        async with factory() as session, session.begin():
            await _business_operation_with_enqueue(session)
            raise RuntimeError("la operación de negocio falló")

    assert await _client_count(engine) == 0
    assert await _outbox_count(engine) == 0


# --- esquema ----------------------------------------------------------------------------------


async def test_orm_model_matches_the_alembic_schema(engine: AsyncEngine) -> None:
    def in_scope(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object):
        table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
        return table == "outbox_messages"

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
