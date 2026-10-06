"""DTOs del contrato de verificación de disponibilidad (RF-09, RF-10, RF-20).

Define la entrada y la salida del puerto ``IAvailabilityPort`` que consumen el
cotizador (E1) y la asignación de elencos (E6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID


class AvailabilityStatus(StrEnum):
    """Resultado de la verificación de disponibilidad."""

    AVAILABLE = "AVAILABLE"
    CONFLICT = "CONFLICT"
    REQUIRES_MANUAL_APPROVAL = "REQUIRES_MANUAL_APPROVAL"


@dataclass(frozen=True)
class InventoryShortageDTO:
    """Falta de stock de un ítem para la ventana solicitada."""

    inventory_item_id: UUID
    requested: int
    available: int


@dataclass(frozen=True)
class AvailabilityRequest:
    """Datos mínimos para verificar disponibilidad de un show solicitado."""

    event_date: date
    start_time: time
    duration_minutes: int
    package_id: UUID


@dataclass(frozen=True)
class AvailabilityResult:
    """Resultado de la verificación de disponibilidad."""

    status: AvailabilityStatus
    simultaneous_count: int = 0
    shortages: tuple[InventoryShortageDTO, ...] = ()

    @property
    def is_available(self) -> bool:
        """Indica si la asignación puede confirmarse de forma automática."""

        return self.status is AvailabilityStatus.AVAILABLE

    @property
    def requires_manual_approval(self) -> bool:
        """Indica si el encargado debe aprobar el sobrecupo."""

        return self.status is AvailabilityStatus.REQUIRES_MANUAL_APPROVAL


@dataclass(frozen=True)
class CrewTransitRequest:
    """Datos para validar el intervalo de tránsito de un elenco entre dos shows."""

    crew_id: UUID
    previous_end: datetime
    candidate_start: datetime
    transit_minutes: int
    override_minutes: int | None = None


@dataclass(frozen=True)
class CrewTransitResult:
    """Resultado de la validación de tránsito entre shows de un mismo elenco."""

    feasible: bool
    required_minutes: int
    available_gap_minutes: int
