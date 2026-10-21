"""DTO de asignación de elenco a evento (tabla ``crew_assignments``)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CrewAssignmentDTO:
    """Fila de ``crew_assignments`` relevante para los overrides de RF-22."""

    id: UUID
    event_id: UUID
    crew_id: UUID
    transit_interval_minutes: int | None
    transit_interval_overridden: bool
