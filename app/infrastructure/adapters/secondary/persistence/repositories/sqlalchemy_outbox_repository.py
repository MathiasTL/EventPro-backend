"""Repositorio del outbox con SQLAlchemy. No confirma: la transacción es del llamador."""

from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.outbox import OutboxStatus
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.persistence.mappers.outbox_mapper import (
    apply_outbox_to_model,
    outbox_to_domain,
    outbox_to_model,
)
from app.infrastructure.adapters.secondary.persistence.models.outbox_message_model import (
    OutboxMessageModel,
)


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: OutboxMessage) -> OutboxMessage:
        self._session.add(outbox_to_model(message))
        await self._session.flush()
        return message

    async def save(self, message: OutboxMessage) -> OutboxMessage:
        row = await self._session.get(OutboxMessageModel, message.id)
        if row is None:
            raise ResourceNotFoundError(f"El mensaje {message.id} no existe")
        apply_outbox_to_model(row, message)
        await self._session.flush()
        return message

    async def get_by_id(
        self, message_id: UUID, *, for_update: bool = False
    ) -> OutboxMessage | None:
        if not for_update:
            row = await self._session.get(OutboxMessageModel, message_id)
        else:
            row = await self._session.scalar(
                select(OutboxMessageModel)
                .where(OutboxMessageModel.id == message_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        return outbox_to_domain(row) if row is not None else None

    async def get_by_external_id(
        self, external_message_id: str, *, for_update: bool = False
    ) -> OutboxMessage | None:
        statement = select(OutboxMessageModel).where(
            OutboxMessageModel.external_message_id == external_message_id
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        row = await self._session.scalar(statement)
        return outbox_to_domain(row) if row is not None else None

    async def find_by_message_reference(self, external_message_id: str) -> OutboxMessage | None:
        row = await self._session.scalar(
            select(OutboxMessageModel)
            .where(
                or_(
                    OutboxMessageModel.external_message_id == external_message_id,
                    OutboxMessageModel.retried_external_message_id == external_message_id,
                )
            )
            .order_by(OutboxMessageModel.created_at.desc())
            .limit(1)
        )
        return outbox_to_domain(row) if row is not None else None

    async def get_many_by_external_ids(
        self, external_message_ids: Collection[str]
    ) -> Mapping[str, OutboxMessage]:
        if not external_message_ids:
            return {}
        rows = await self._session.scalars(
            select(OutboxMessageModel)
            .where(
                or_(
                    OutboxMessageModel.external_message_id.in_(external_message_ids),
                    OutboxMessageModel.retried_external_message_id.in_(external_message_ids),
                )
            )
            .order_by(OutboxMessageModel.created_at)
            .execution_options(populate_existing=True)
        )
        found: dict[str, OutboxMessage] = {}
        for row in rows:
            message = outbox_to_domain(row)
            for reference in (row.external_message_id, row.retried_external_message_id):
                if reference is not None and reference in external_message_ids:
                    found[reference] = message
        return found

    async def list_unsent_for_recipient(
        self, phone: PhoneNumber, *, limit: int = 50
    ) -> Sequence[OutboxMessage]:
        rows = await self._session.scalars(
            select(OutboxMessageModel)
            .where(
                OutboxMessageModel.recipient_phone == phone.value,
                OutboxMessageModel.status.in_(
                    (OutboxStatus.PENDING.value, OutboxStatus.FAILED.value)
                ),
            )
            .order_by(OutboxMessageModel.created_at)
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [outbox_to_domain(row) for row in rows]

    async def claim_due(
        self, *, now: datetime, limit: int, lease: timedelta
    ) -> Sequence[OutboxMessage]:
        rows = (
            await self._session.scalars(
                select(OutboxMessageModel)
                .where(
                    OutboxMessageModel.status == OutboxStatus.PENDING.value,
                    OutboxMessageModel.next_attempt_at <= now,
                )
                .order_by(OutboxMessageModel.next_attempt_at, OutboxMessageModel.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).all()
        for row in rows:
            row.next_attempt_at = now + lease
        await self._session.flush()
        return [outbox_to_domain(row) for row in rows]


class SqlAlchemyOutboxTransaction:
    """Abre transacciones cortas: confirma al salir sin error y revierte si el bloque falla."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> AbstractAsyncContextManager[IOutboxRepositoryPort]:
        return self._open()

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[IOutboxRepositoryPort]:
        async with self._session_factory() as session, session.begin():
            yield SqlAlchemyOutboxRepository(session)
