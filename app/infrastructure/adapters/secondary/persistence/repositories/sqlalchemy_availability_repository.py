"""Consultas de disponibilidad sobre PostgreSQL (E3).

Alimenta al motor de disponibilidad con el inventario que consume un paquete, las
reservas activas que se solapan con la ventana solicitada y los eventos que cuentan
para el umbral de shows simultáneos (RN-04).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence.models.availability_models import (
    InventoryReservationModel,
)
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    InventoryItemModel,
    PackageInventoryItemModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel


@dataclass(frozen=True)
class InventoryRequirementRow:
    """Requerimiento de inventario de un paquete, con el stock total del ítem."""

    inventory_item_id: UUID
    quantity: int
    total_stock: int
    name: str


@dataclass(frozen=True)
class EventWindowRow:
    """Evento que cuenta para el umbral, con su ventana programada."""

    event_id: UUID
    status: str
    window: TimeWindow


class SqlAlchemyAvailabilityRepository:
    """Consultas de disponibilidad (inventario, reservas y eventos)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_package_inventory_requirements(
        self, package_id: UUID
    ) -> Sequence[InventoryRequirementRow]:
        """Inventario que consume un paquete por evento, con el stock total del ítem.

        No filtra por ``is_active``: un ítem dado de baja que siga consumido por un
        paquete activo debe seguir validando su stock.
        """

        stmt = (
            select(
                PackageInventoryItemModel.inventory_item_id,
                PackageInventoryItemModel.quantity,
                InventoryItemModel.total_stock,
                InventoryItemModel.name,
            )
            .join(
                InventoryItemModel,
                InventoryItemModel.id == PackageInventoryItemModel.inventory_item_id,
            )
            .where(PackageInventoryItemModel.package_id == package_id)
            .order_by(PackageInventoryItemModel.inventory_item_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return tuple(
            InventoryRequirementRow(
                inventory_item_id=row.inventory_item_id,
                quantity=row.quantity,
                total_stock=row.total_stock,
                name=row.name,
            )
            for row in rows
        )

    async def list_active_reservations(
        self, inventory_item_ids: Sequence[UUID], window: TimeWindow
    ) -> Sequence[InventoryReservationModel]:
        """Reservas ``ACTIVE`` de los ítems indicados que se solapan con la ventana."""

        if not inventory_item_ids:
            return ()
        stmt = (
            select(InventoryReservationModel)
            .where(
                InventoryReservationModel.inventory_item_id.in_(inventory_item_ids),
                InventoryReservationModel.status == "ACTIVE",
                InventoryReservationModel.starts_at < window.end,
                InventoryReservationModel.ends_at > window.start,
            )
            .order_by(InventoryReservationModel.starts_at)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_countable_events(self, window: TimeWindow) -> Sequence[EventWindowRow]:
        """Eventos que se solapan con la ventana y cuentan para el umbral.

        Solo cuentan los eventos no cancelados: todo evento nace con el adelanto
        validado (RN-04), por lo que no se filtra por pagos.
        """

        start_date = window.start.date() - timedelta(days=1)
        end_date = window.end.date() + timedelta(days=1)
        stmt = (
            select(EventModel)
            .where(
                EventModel.event_date >= start_date,
                EventModel.event_date <= end_date,
                EventModel.status != "CANCELLED",
            )
            .order_by(EventModel.event_date, EventModel.start_time)
        )
        events = (await self._session.execute(stmt)).scalars().all()
        return tuple(
            EventWindowRow(
                event_id=event.id,
                status=event.status,
                window=TimeWindow.from_event(event.event_date, event.start_time, event.end_time),
            )
            for event in events
            if TimeWindow.from_event(event.event_date, event.start_time, event.end_time).overlaps(
                window
            )
        )
