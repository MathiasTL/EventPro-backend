"""Cronograma y persistencia transaccional del inicio del evento sobre PostgreSQL."""

from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from sqlalchemy import case, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.event_extension_dto import VerifiedExtensionTotals
from app.application.dtos.event_occupancy_dto import EventOccupancy
from app.application.dtos.event_schedule_dto import EventScheduleFilters
from app.domain.entities.event import Event
from app.domain.entities.event_extension import EventExtension
from app.domain.entities.payment import Payment, PaymentConcept, PaymentValidationStatus
from app.domain.exceptions.event_exceptions import (
    ExtensionPaymentMismatchError,
    InvalidEventStateError,
)
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.mappers.event_extension_mapper import (
    extension_to_model,
)
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_domain
from app.infrastructure.adapters.secondary.persistence.mappers.payment_mapper import (
    payment_to_model,
)
from app.infrastructure.adapters.secondary.persistence.models.event_extension_model import (
    EventExtensionModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_occupancy,
)


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rollback_operation(self) -> None:
        await self._session.rollback()

    async def lock_availability(self) -> None:
        await sqlalchemy_event_occupancy.SqlAlchemyEventOccupancy(self._session).lock_availability()

    async def load_occupancy(self, event: Event, added_minutes: int) -> EventOccupancy:
        return await sqlalchemy_event_occupancy.SqlAlchemyEventOccupancy(
            self._session
        ).load_occupancy(event, added_minutes)

    async def can_discard_extension_evidence(self, payment_id: UUID) -> bool:
        """Consulta PostgreSQL después del rollback; no supone que un commit fallido no llegó."""
        return (
            await self._session.scalar(select(PaymentModel.id).where(PaymentModel.id == payment_id))
        ) is None

    async def save_extension(
        self, event: Event, extension: EventExtension, payment: Payment
    ) -> None:
        try:
            if (
                event.status is not EventStatus.EXTENDED
                or extension.event_id != event.id
                or payment.id != extension.payment_id
                or payment.event_id != event.id
                or payment.quote_id != event.quote_id
                or payment.concept is not PaymentConcept.EXTENSION
                or payment.validation_status is not PaymentValidationStatus.VERIFIED
                or payment.amount != extension.agreed_rate
            ):
                raise ExtensionPaymentMismatchError(
                    "La extensión no coincide con su pago o evento."
                )
            self._session.add(payment_to_model(payment))
            await self._session.flush()
            self._session.add(extension_to_model(extension))
            await self._session.flush()
            stmt = (
                update(EventModel)
                .where(
                    EventModel.id == event.id,
                    EventModel.status.in_(
                        (EventStatus.IN_PROGRESS.value, EventStatus.EXTENDED.value)
                    ),
                    EventModel.extra_minutes_total + extension.extra_minutes
                    == event.extra_minutes_total,
                    EventModel.extra_hours_amount + extension.agreed_rate.amount
                    == event.extra_hours_amount.amount,
                    EventModel.final_total_amount + extension.agreed_rate.amount
                    == event.final_total_amount.amount,
                )
                .values(
                    status=event.status.value,
                    extra_minutes_total=event.extra_minutes_total,
                    extra_hours_amount=event.extra_hours_amount.amount,
                    final_total_amount=event.final_total_amount.amount,
                )
                .returning(EventModel.id)
            )
            if (await self._session.execute(stmt)).scalar_one_or_none() is None:
                raise InvalidEventStateError("El evento ya no admite esta extensión.")
            await self._session.execute(
                update(InventoryReservationModel)
                .where(
                    InventoryReservationModel.event_id == event.id,
                    InventoryReservationModel.status == "ACTIVE",
                )
                .values(
                    ends_at=InventoryReservationModel.ends_at
                    + timedelta(minutes=extension.extra_minutes)
                )
            )
            await self._session.commit()
        except BaseException:
            await self._session.rollback()
            raise

    async def get_verified_extension_totals(self, event_id: UUID) -> VerifiedExtensionTotals:
        invalid = or_(
            PaymentModel.id.is_(None),
            PaymentModel.event_id != event_id,
            PaymentModel.quote_id != EventModel.quote_id,
            PaymentModel.concept != PaymentConcept.EXTENSION.value,
            PaymentModel.validation_status != PaymentValidationStatus.VERIFIED.value,
            PaymentModel.amount != EventExtensionModel.agreed_rate,
        )
        extensions = (
            select(
                func.count(EventExtensionModel.id).label("count"),
                func.coalesce(func.sum(EventExtensionModel.extra_minutes), 0).label("minutes"),
                func.coalesce(func.sum(EventExtensionModel.agreed_rate), 0).label("amount"),
                func.coalesce(func.sum(case((invalid, 1), else_=0)), 0).label("invalid"),
            )
            .join(EventModel, EventModel.id == EventExtensionModel.event_id)
            .outerjoin(PaymentModel, PaymentModel.id == EventExtensionModel.payment_id)
            .where(EventExtensionModel.event_id == event_id)
        ).subquery()
        payments = (
            select(func.count(PaymentModel.id).label("count"))
            .where(
                PaymentModel.event_id == event_id,
                PaymentModel.concept == PaymentConcept.EXTENSION.value,
            )
            .subquery()
        )
        row = (
            await self._session.execute(
                select(
                    extensions.c.amount,
                    extensions.c.minutes,
                    extensions.c.invalid,
                    extensions.c.count,
                    payments.c.count,
                ).select_from(extensions.join(payments, true()))
            )
        ).one()
        if row.invalid or row[3] != row[4]:
            raise ExtensionPaymentMismatchError(
                "Las extensiones no coinciden con sus pagos verificados."
            )
        return VerifiedExtensionTotals(Money(row.amount), row.minutes)

    async def save_settlement(self, event: Event) -> None:
        try:
            if event.status is not EventStatus.SETTLED:
                raise InvalidEventStateError("El evento debe haber completado la liquidación.")
            stmt = (
                update(EventModel)
                .where(
                    EventModel.id == event.id,
                    EventModel.status.in_(
                        (EventStatus.IN_PROGRESS.value, EventStatus.EXTENDED.value)
                    ),
                    EventModel.extra_minutes_total == event.extra_minutes_total,
                    EventModel.extra_hours_amount == event.extra_hours_amount.amount,
                    EventModel.final_total_amount == event.final_total_amount.amount,
                    EventModel.advance_paid == event.advance_paid.amount,
                    EventModel.pre_show_balance_paid == event.pre_show_balance_paid.amount,
                    EventModel.legacy_extra_hours_amount == event.legacy_extra_hours_amount.amount,
                )
                .values(status=event.status.value)
                .returning(EventModel.id)
            )
            if (await self._session.execute(stmt)).scalar_one_or_none() is None:
                raise InvalidEventStateError("El evento ya no admite esta liquidación.")
            await self._session.commit()
        except BaseException:
            await self._session.rollback()
            raise

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
