"""Cronograma y persistencia transaccional del inicio del evento sobre PostgreSQL."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.event_schedule_dto import EventScheduleFilters
from app.domain.entities.event import Event
from app.domain.exceptions.event_exceptions import InvalidEventStateError
from app.domain.value_objects.event_status import EventStatus
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_domain
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id_for_update(self, event_id: UUID) -> Event | None:
        stmt = (
            select(EventModel)
            .where(EventModel.id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return event_to_domain(row) if row is not None else None

    async def save_start(self, event: Event) -> None:
        """Confirma juntos los tres campos de inicio; revierte también un commit fallido."""
        try:
            if event.status is not EventStatus.IN_PROGRESS or event.actual_start_time is None:
                raise InvalidEventStateError(
                    "El evento debe haber completado la transición de inicio."
                )
            stmt = (
                update(EventModel)
                .where(
                    EventModel.id == event.id,
                    EventModel.status.in_(
                        (EventStatus.SCHEDULED.value, EventStatus.AWAITING_BALANCE.value)
                    ),
                    EventModel.actual_start_time.is_(None),
                )
                .values(
                    status=event.status.value,
                    pre_show_balance_paid=event.pre_show_balance_paid.amount,
                    actual_start_time=event.actual_start_time,
                )
                .returning(EventModel.id)
            )
            if (await self._session.execute(stmt)).scalar_one_or_none() is None:
                raise InvalidEventStateError("El evento ya no admite un inicio.")
            await self._session.commit()
        except BaseException:
            await self._session.rollback()
            raise

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
