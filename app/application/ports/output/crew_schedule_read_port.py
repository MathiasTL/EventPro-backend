from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from app.application.dtos.event_schedule_dto import CrewScheduleDTO


class ICrewScheduleReadPort(Protocol):
    async def get_assigned_event_ids(self, user_id: UUID) -> frozenset[UUID]:
        """IDs autorizados por las asignaciones del elenco vinculado al usuario."""

    async def get_crews(
        self, event_ids: frozenset[UUID]
    ) -> Mapping[UUID, tuple[CrewScheduleDTO, ...]]:
        """Elencos de cada evento solicitado; sin asignaciones devuelve tupla vacía."""
