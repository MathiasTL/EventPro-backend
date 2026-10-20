"""Fotografía pura de la ocupación necesaria para ampliar un evento."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.services.inventory_availability import InventoryRequest, InventoryReservation
from app.domain.value_objects.time_window import TimeWindow


@dataclass(frozen=True)
class InventoryOccupancy:
    total_stock: int
    request: InventoryRequest
    reservations: tuple[InventoryReservation, ...]


@dataclass(frozen=True)
class CrewOccupancy:
    crew_id: UUID
    window: TimeWindow
    transit_interval_minutes: int | None


@dataclass(frozen=True)
class EventOccupancy:
    simultaneous_windows: tuple[TimeWindow, ...] = ()
    inventory: tuple[InventoryOccupancy, ...] = ()
    crews: tuple[CrewOccupancy, ...] = ()
