"""Ocupación real del baseline, leída bajo el candado transaccional de disponibilidad."""

from datetime import timedelta

from sqlalchemy import DateTime, case, cast, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.event_occupancy_dto import (
    CrewOccupancy,
    EventOccupancy,
    InventoryOccupancy,
)
from app.domain.entities.event import Event
from app.domain.services.inventory_availability import InventoryRequest, InventoryReservation
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_domain
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    InventoryItemModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    CrewAssignmentModel,
    InventoryReservationModel,
)

# Los futuros escritores E3 deben adquirir este mismo candado antes del evento.
AVAILABILITY_LOCK_KEY = 180018


class SqlAlchemyEventOccupancy:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_availability(self) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": AVAILABILITY_LOCK_KEY}
        )

    async def load_occupancy(self, event: Event, added_minutes: int) -> EventOccupancy:
        window = event.time_window
        end = (
            cast(EventModel.event_date + EventModel.end_time, DateTime())
            + case(
                (EventModel.end_time < EventModel.start_time, timedelta(days=1)), else_=timedelta()
            )
            + EventModel.extra_minutes_total * text("INTERVAL '1 minute'")
        )
        start = cast(EventModel.event_date + EventModel.start_time, DateTime())
        events = (
            await self._session.scalars(
                select(EventModel).where(
                    EventModel.id != event.id,
                    EventModel.status != EventStatus.CANCELLED.value,
                    EventModel.advance_paid > 0,
                    start < window.end,
                    end > window.start,
                )
            )
        ).all()
        windows = tuple(event_to_domain(row).time_window for row in events)
        own_crew_ids = select(CrewAssignmentModel.crew_id).where(
            CrewAssignmentModel.event_id == event.id
        )
        assigned = (
            await self._session.execute(
                select(CrewAssignmentModel, EventModel)
                .join(EventModel, CrewAssignmentModel.event_id == EventModel.id)
                .where(
                    CrewAssignmentModel.crew_id.in_(own_crew_ids),
                    EventModel.id != event.id,
                    EventModel.status != EventStatus.CANCELLED.value,
                )
            )
        ).all()
        crews = tuple(
            CrewOccupancy(
                row.crew_id, event_to_domain(other).time_window, row.transit_interval_minutes
            )
            for row, other in assigned
        )
        current = (
            await self._session.execute(
                select(InventoryReservationModel, InventoryItemModel.total_stock)
                .join(
                    InventoryItemModel,
                    InventoryItemModel.id == InventoryReservationModel.inventory_item_id,
                )
                .where(
                    InventoryReservationModel.event_id == event.id,
                    InventoryReservationModel.status == "ACTIVE",
                )
            )
        ).all()
        items = {row.inventory_item_id for row, _stock in current}
        other_reservations = (
            (
                await self._session.scalars(
                    select(InventoryReservationModel).where(
                        InventoryReservationModel.inventory_item_id.in_(items),
                        InventoryReservationModel.event_id != event.id,
                        InventoryReservationModel.status == "ACTIVE",
                    )
                )
            ).all()
            if items
            else []
        )
        external = tuple(
            InventoryReservation(
                row.inventory_item_id, row.quantity, TimeWindow(row.starts_at, row.ends_at)
            )
            for row in other_reservations
        )
        proposed = tuple(
            InventoryReservation(
                row.inventory_item_id,
                row.quantity,
                TimeWindow(row.starts_at, row.ends_at + timedelta(minutes=added_minutes)),
            )
            for row, _stock in current
        )
        inventory = tuple(
            InventoryOccupancy(
                stock,
                InventoryRequest(
                    reservation.inventory_item_id, reservation.quantity, reservation.window
                ),
                external
                + tuple(other for index, other in enumerate(proposed) if index != position),
            )
            for position, (reservation, (_row, stock)) in enumerate(
                zip(proposed, current, strict=True)
            )
        )
        return EventOccupancy(windows, inventory, crews)
