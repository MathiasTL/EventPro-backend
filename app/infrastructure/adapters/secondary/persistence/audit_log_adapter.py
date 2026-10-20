from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dtos.audit_log_dto import AuditLogFilters
from app.domain.entities.audit_log import AuditLog
from app.infrastructure.adapters.secondary.persistence.models.audit_log import (
    AuditLog as AuditLogModel,
)


def _day_start(day: date) -> datetime:
    """Primer instante (UTC) del día indicado."""
    return datetime.combine(day, time.min, tzinfo=UTC)


def _day_end(day: date) -> datetime:
    """Primer instante (UTC) del día siguiente: límite exclusivo de `to_date`.

    `date.max` no admite sumar un día (`OverflowError`), así que se devuelve el
    último instante posible: incluye toda la jornada de `to_date` sin error interno.
    """
    if day == date.max:
        return datetime.max.replace(tzinfo=UTC)
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC)


class SQLAlchemyAuditLogAdapter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, entry: AuditLog) -> None:
        async with self._session_factory() as session:
            session.add(
                AuditLogModel(
                    id=entry.id,
                    user_id=entry.user_id,
                    action=entry.action,
                    entity_name=entry.entity_name,
                    entity_id=entry.entity_id,
                    old_values=entry.old_values,
                    new_values=entry.new_values,
                )
            )
            await session.commit()

    async def list_entries(self, filters: AuditLogFilters) -> Sequence[AuditLog]:
        stmt = select(AuditLogModel).order_by(
            AuditLogModel.created_at.desc(), AuditLogModel.id.desc()
        )
        stmt = self._apply_filters(stmt, filters)
        page_size = max(1, min(filters.page_size, 100))
        stmt = stmt.offset((max(1, filters.page) - 1) * page_size).limit(page_size)
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return tuple(self._to_domain(row) for row in result.scalars().all())

    async def count_entries(self, filters: AuditLogFilters) -> int:
        stmt = select(func.count()).select_from(AuditLogModel)
        stmt = self._apply_filters(stmt, filters)
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return int(result.scalar_one())

    def _apply_filters(self, stmt: Select[Any], filters: AuditLogFilters) -> Select[Any]:
        if filters.action is not None:
            stmt = stmt.where(AuditLogModel.action == filters.action)
        if filters.entity_name is not None:
            stmt = stmt.where(AuditLogModel.entity_name == filters.entity_name)
        if filters.entity_id is not None:
            stmt = stmt.where(AuditLogModel.entity_id == filters.entity_id)
        if filters.user_id is not None:
            stmt = stmt.where(AuditLogModel.user_id == filters.user_id)
        if filters.from_date is not None:
            stmt = stmt.where(AuditLogModel.created_at >= _day_start(filters.from_date))
        if filters.to_date is not None:
            stmt = stmt.where(AuditLogModel.created_at < _day_end(filters.to_date))
        return stmt

    @staticmethod
    def _to_domain(row: AuditLogModel) -> AuditLog:
        return AuditLog(
            id=row.id,
            action=row.action,
            entity_name=row.entity_name,
            entity_id=row.entity_id,
            user_id=row.user_id,
            old_values=row.old_values,
            new_values=row.new_values,
            created_at=row.created_at,
        )
