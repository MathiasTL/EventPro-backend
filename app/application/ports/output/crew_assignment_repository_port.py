from typing import Protocol
from uuid import UUID

from app.application.dtos.crew_assignment_dto import CrewAssignmentDTO


class ICrewAssignmentRepositoryPort(Protocol):
    """Persistencia de ``crew_assignments`` para el override de intervalo (RF-22, US-20)."""

    async def get_by_id(self, assignment_id: UUID) -> CrewAssignmentDTO | None:
        """Devuelve la asignación, o None si no existe."""

    async def override_transit_interval(
        self, assignment_id: UUID, *, transit_interval_minutes: int
    ) -> CrewAssignmentDTO:
        """Sobrescribe el intervalo y marca ``transit_interval_overridden = true``.

        Lanza ``ResourceNotFoundError`` si la asignación no existe.
        """
