"""Avisos de entrega de Chatwoot sobre PostgreSQL 16 real: transacciones y orden de llegada."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.dtos.gateway_event_dto import GatewayEventOutcome
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.application.use_cases.messaging.process_gateway_event import ProcessGatewayEvent
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.value_objects.outbox import DeliveryStatus
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_event_gateway import (  # noqa: E501
    ChatwootEventGateway,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxRepository,
    SqlAlchemyOutboxTransaction,
)
from tests.chatwoot_fixture_support import load_fixture
from tests.domain.outbox_support import NOW, make_message

from ._support import run_migrations

pytestmark = pytest.mark.integration

EXTERNAL_ID = "4821"
RECEIVED_AT = datetime(2026, 10, 12, 14, 5, tzinfo=UTC)
# Hora de actualización que trae el fixture ``message_updated_delivered``.
DELIVERED_AT = datetime(2026, 10, 12, 14, 1, tzinfo=UTC)


def _body(name: str) -> bytes:
    return json.dumps(load_fixture(name)["body"]).encode()


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


def _use_case(transaction: SqlAlchemyOutboxTransaction | object) -> ProcessGatewayEvent:
    return ProcessGatewayEvent(
        transaction=transaction,  # type: ignore[arg-type]
        gateway=ChatwootEventGateway(None),
    )


def _sent_message() -> OutboxMessage:
    message = make_message()
    message.mark_sent(external_message_id=EXTERNAL_ID, conversation_id=57, now=NOW)
    return message


async def _add(factory: async_sessionmaker[AsyncSession], message: OutboxMessage) -> None:
    async with factory() as session, session.begin():
        await SqlAlchemyOutboxRepository(session).add(message)


async def _reload(
    factory: async_sessionmaker[AsyncSession], message: OutboxMessage
) -> OutboxMessage:
    async with factory() as session:
        loaded = await SqlAlchemyOutboxRepository(session).get_by_id(message.id)
    assert loaded is not None
    return loaded


class _SaveThenFailRepository:
    """Guarda de verdad (hace el UPDATE) y falla después, dentro de la misma transacción."""

    def __init__(self, inner: SqlAlchemyOutboxRepository) -> None:
        self._inner = inner

    async def get_by_external_id(
        self, external_message_id: str, *, for_update: bool = False
    ) -> OutboxMessage | None:
        return await self._inner.get_by_external_id(external_message_id, for_update=for_update)

    async def save(self, message: OutboxMessage) -> OutboxMessage:
        await self._inner.save(message)
        raise RuntimeError("Fallo simulado tras el UPDATE")


class _SaveThenFailTransaction:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    def __call__(self) -> AbstractAsyncContextManager[IOutboxRepositoryPort]:
        return self._open()

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[IOutboxRepositoryPort]:
        async with self._factory() as session, session.begin():
            yield _SaveThenFailRepository(SqlAlchemyOutboxRepository(session))  # type: ignore[misc]


async def test_a_delivered_notice_persists_the_status_and_the_payload_time(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    message = _sent_message()
    await _add(factory, message)

    outcome = await _use_case(SqlAlchemyOutboxTransaction(factory)).execute(
        raw_body=_body("message_updated_delivered"), received_at=RECEIVED_AT
    )

    loaded = await _reload(factory, message)
    assert outcome is GatewayEventOutcome.APPLIED
    assert loaded.delivery_status is DeliveryStatus.DELIVERED
    assert loaded.delivered_at == DELIVERED_AT


async def test_a_read_notice_after_delivered_moves_forward_and_a_late_delivered_does_not_back(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    message = _sent_message()
    await _add(factory, message)
    use_case = _use_case(SqlAlchemyOutboxTransaction(factory))

    read = await use_case.execute(raw_body=_body("message_updated_read"), received_at=RECEIVED_AT)
    late = await use_case.execute(
        raw_body=_body("message_updated_delivered"), received_at=RECEIVED_AT
    )

    loaded = await _reload(factory, message)
    assert (read, late) == (GatewayEventOutcome.APPLIED, GatewayEventOutcome.IGNORED)
    assert loaded.delivery_status is DeliveryStatus.READ
    assert loaded.read_at is not None


async def test_a_notice_for_a_row_already_read_leaves_it_unchanged(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    message = _sent_message()
    message.record_delivery(status=DeliveryStatus.READ, error=None, at=NOW)
    await _add(factory, message)
    before = await _reload(factory, message)

    outcome = await _use_case(SqlAlchemyOutboxTransaction(factory)).execute(
        raw_body=_body("message_updated_delivered"), received_at=RECEIVED_AT
    )

    assert outcome is GatewayEventOutcome.IGNORED
    assert await _reload(factory, message) == before


async def test_a_repository_failure_during_save_rolls_back_and_propagates(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    message = _sent_message()
    await _add(factory, message)

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        await _use_case(_SaveThenFailTransaction(factory)).execute(
            raw_body=_body("message_updated_delivered"), received_at=RECEIVED_AT
        )

    loaded = await _reload(factory, message)
    assert loaded.delivery_status is None
    assert loaded.delivered_at is None


async def test_a_notice_before_sent_is_unknown_and_applies_once_the_row_exists(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    use_case = _use_case(SqlAlchemyOutboxTransaction(factory))
    body = _body("message_updated_delivered")

    first = await use_case.execute(raw_body=body, received_at=RECEIVED_AT)
    message = _sent_message()
    await _add(factory, message)
    second = await use_case.execute(raw_body=body, received_at=RECEIVED_AT)

    assert first is GatewayEventOutcome.UNKNOWN_MESSAGE
    assert second is GatewayEventOutcome.APPLIED
    assert (await _reload(factory, message)).delivery_status is DeliveryStatus.DELIVERED
