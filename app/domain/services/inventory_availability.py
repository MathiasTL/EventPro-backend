"""Servicio de dominio: disponibilidad de inventario en una ventana de tiempo.

RF-09 / US-08: el stock disponible de un ítem es ``total_stock`` menos la suma de las
cantidades de las reservas **ACTIVAS** que se solapan con la ventana solicitada. La
verificación se ejecuta bajo el lock distribuido (ADR-06) para evitar la doble
reserva concurrente, pero el cálculo en sí es puro y no conoce la base de datos.

El llamador es responsable de entregar únicamente reservas ``ACTIVE`` (las
``RELEASED`` de un evento cancelado no ocupan stock).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.value_objects.time_window import TimeWindow


@dataclass(frozen=True)
class InventoryReservation:
    """Reserva activa de unidades de un ítem en una ventana de tiempo."""

    inventory_item_id: UUID
    quantity: int
    window: TimeWindow

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity de la reserva debe ser mayor que cero")


@dataclass(frozen=True)
class InventoryRequest:
    """Necesidad de inventario de un paquete para una ventana de tiempo."""

    inventory_item_id: UUID
    quantity: int
    window: TimeWindow

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity solicitada debe ser mayor que cero")


@dataclass(frozen=True)
class InventoryCheck:
    """Resultado de verificar un requerimiento de inventario."""

    is_available: bool
    requested_quantity: int
    available_quantity: int

    @property
    def missing_quantity(self) -> int:
        """Unidades que faltan para cubrir la solicitud (0 si alcanza)."""

        return max(0, self.requested_quantity - self.available_quantity)


class InventoryAvailabilityService:
    """Calcula el stock disponible y si cubre una solicitud."""

    def reserved_quantity(
        self,
        inventory_item_id: UUID,
        reservations: tuple[InventoryReservation, ...],
        window: TimeWindow,
    ) -> int:
        """Unidades reservadas (activas) de un ítem que se solapan con la ventana."""

        return sum(
            reservation.quantity
            for reservation in reservations
            if reservation.inventory_item_id == inventory_item_id
            and reservation.window.overlaps(window)
        )

    def available_quantity(
        self,
        total_stock: int,
        inventory_item_id: UUID,
        reservations: tuple[InventoryReservation, ...],
        window: TimeWindow,
    ) -> int:
        """Unidades disponibles de un ítem en la ventana (nunca negativas)."""

        if total_stock < 0:
            raise ValueError("total_stock no puede ser negativo")
        reserved = self.reserved_quantity(inventory_item_id, reservations, window)
        return max(0, total_stock - reserved)

    def check(
        self,
        total_stock: int,
        reservations: tuple[InventoryReservation, ...],
        request: InventoryRequest,
    ) -> InventoryCheck:
        """Verifica si el stock cubre la solicitud."""

        available = self.available_quantity(
            total_stock,
            request.inventory_item_id,
            reservations,
            request.window,
        )
        return InventoryCheck(
            is_available=available >= request.quantity,
            requested_quantity=request.quantity,
            available_quantity=available,
        )
