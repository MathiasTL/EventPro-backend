"""Enviar y reintentar sobre PostgreSQL real: el mensaje y su auditoría comparten transacción."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.dtos.messaging_dto import ConversationStatus
from app.application.services.audit_service import AuditService
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.application.use_cases.messaging.retry_message import RetryMessage
from app.application.use_cases.messaging.send_conversation_message import (
    RetryConversationMessage,
    SendConversationMessage,
)
from app.domain.entities.audit_log import AuditLog
from app.domain.value_objects.outbox import DeliveryStatus, OutboxStatus
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from app.infrastructure.adapters.secondary.persistence.audit_log_adapter import (
    SessionAuditRecorder,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_conversation_link_repository import (  # noqa: E501
    SqlAlchemyConversationLinkRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxRepository,
)
from tests.application.outbox_support import FixedClock
from tests.domain.outbox_support import NOW

from ._support import insert_user, run_migrations

pytestmark = pytest.mark.integration

PHONE = PhoneNumber("+51999888777")


class _FailsAfterRecording:
    """Registra en la sesión y falla después: simula una caída tras escribir la auditoría."""

    def __init__(self, session: AsyncSession) -> None:
        self._inner = SessionAuditRecorder(session)

    async def record(self, entry: AuditLog) -> None:
        await self._inner.record(entry)
        raise RuntimeError("caída tras auditar")


@pytest.fixture(scope="module")
def migrated_url(database_url: str) -> str:
    run_migrations(database_url)
    return database_url


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(migrated_url)
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM outbox_messages"))
        await connection.execute(text("DELETE FROM audit_logs"))
        await connection.execute(text("DELETE FROM conversation_links"))
    yield engine
    await engine.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _messaging(factory: async_sessionmaker[AsyncSession], user: UUID) -> FakeMessagingAdapter:
    """Conversación 1 abierta, asignada a ``user`` en la base."""

    messaging = FakeMessagingAdapter()
    messaging.receive_text(PHONE, "Hola")
    await messaging.set_conversation_status(1, ConversationStatus.HUMAN)
    async with factory() as session, session.begin():
        links = SqlAlchemyConversationLinkRepository(session)
        await links.ensure(1, None, NOW)
        assert await links.claim(1, user, None)
    return messaging


def _send(
    session: AsyncSession, messaging: FakeMessagingAdapter, audit: AuditService
) -> SendConversationMessage:
    outbox = SqlAlchemyOutboxRepository(session)
    return SendConversationMessage(
        messaging,
        SqlAlchemyConversationLinkRepository(session),
        outbox,
        audit,
        EnqueueMessage(outbox, FixedClock()),
    )


async def _count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as connection:
        return int(await connection.scalar(text(f"SELECT count(*) FROM {table}")) or 0)


async def test_send_commits_the_message_and_its_audit_together(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await insert_user(engine, "ENCARGADO")
    messaging = await _messaging(factory, user)

    async with factory() as session, session.begin():
        send = _send(session, messaging, AuditService(SessionAuditRecorder(session)))
        queued = await send.execute(1, user_id=user, content="Hola, claro")

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT author_user_id, status FROM outbox_messages WHERE id = :id"),
                {"id": queued.outbox_id},
            )
        ).one()
        audit = (
            await connection.execute(
                text("SELECT user_id, entity_name, new_values FROM audit_logs")
            )
        ).one()
    assert (row.author_user_id, row.status) == (user, "PENDING")
    assert (audit.user_id, audit.entity_name) == (user, "outbox_message")
    assert "Hola" not in str(audit.new_values)


async def test_a_failure_after_the_audit_rolls_back_the_enqueue_too(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await insert_user(engine, "ENCARGADO")
    messaging = await _messaging(factory, user)

    with pytest.raises(RuntimeError):
        async with factory() as session, session.begin():
            send = _send(session, messaging, AuditService(_FailsAfterRecording(session)))
            await send.execute(1, user_id=user, content="Hola")

    assert await _count(engine, "outbox_messages") == 0
    assert await _count(engine, "audit_logs") == 0


async def test_retry_persists_the_kept_external_id_and_the_retry_audit(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await insert_user(engine, "ENCARGADO")
    messaging = await _messaging(factory, user)
    async with factory() as session, session.begin():
        queued = await _send(
            session, messaging, AuditService(SessionAuditRecorder(session))
        ).execute(1, user_id=user, content="Hola")
    async with factory() as session, session.begin():
        outbox = SqlAlchemyOutboxRepository(session)
        row = await outbox.get_by_id(queued.outbox_id, for_update=True)
        assert row is not None
        row.mark_sent(external_message_id="cw-77", conversation_id=1, now=NOW)
        row.record_delivery(status=DeliveryStatus.FAILED, error="x", at=NOW)
        await outbox.save(row)

    async with factory() as session, session.begin():
        outbox = SqlAlchemyOutboxRepository(session)
        retry = RetryConversationMessage(
            messaging,
            SqlAlchemyConversationLinkRepository(session),
            outbox,
            AuditService(SessionAuditRecorder(session)),
            RetryMessage(outbox, FixedClock()),
        )
        await retry.execute(1, queued.outbox_id, user_id=user)

    async with factory() as session:
        outbox = SqlAlchemyOutboxRepository(session)
        stored = await outbox.get_by_id(queued.outbox_id)
        by_reference = await outbox.get_many_by_external_ids(["cw-77"])
    assert stored is not None
    assert (stored.status, stored.external_message_id) == (OutboxStatus.PENDING, None)
    assert stored.retried_external_message_id == "cw-77"
    assert by_reference["cw-77"].id == queued.outbox_id
    assert await _count(engine, "audit_logs") == 2
