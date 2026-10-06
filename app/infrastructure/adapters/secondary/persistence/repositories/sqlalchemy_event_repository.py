"""Consulta del cronograma con filtros y alcance autorizado aplicados en SQL."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.event_schedule_dto import EventScheduleFilters
from app.domain.entities.event import Event
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_domain
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_schedule(
        self, filters: EventScheduleFilters, *, event_ids: frozenset[UUID] | None = None
    ) -> Sequence[Event]:
        if event_ids is not None and not event_ids:
            return ()
        stmt = select(EventModel).order_by(
            EventModel.event_date, EventModel.start_time, EventModel.id
        )
        if filters.from_date is not None:
            stmt = stmt.where(EventModel.event_date >= filters.from_date)
        if filters.to_date is not None:
            stmt = stmt.where(EventModel.event_date <= filters.to_date)
        if filters.status is not None:
            stmt = stmt.where(EventModel.status == filters.status.value)
        if event_ids is not None:
            stmt = stmt.where(EventModel.id.in_(event_ids))
        result = await self._session.execute(stmt)
        return tuple(event_to_domain(row) for row in result.scalars().all())
