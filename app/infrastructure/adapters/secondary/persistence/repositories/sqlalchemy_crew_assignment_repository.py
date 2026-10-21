"""Repositorio de asignaciones de elenco con SQLAlchemy (RF-22, US-20)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.crew_assignment_dto import CrewAssignmentDTO
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    CrewAssignmentModel,
)


def _to_dto(row: CrewAssignmentModel) -> CrewAssignmentDTO:
    return CrewAssignmentDTO(
        id=row.id,
        event_id=row.event_id,
        crew_id=row.crew_id,
        transit_interval_minutes=row.transit_interval_minutes,
        transit_interval_overridden=row.transit_interval_overridden,
    )


class SqlAlchemyCrewAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, assignment_id: UUID) -> CrewAssignmentDTO | None:
        row = await self._session.get(CrewAssignmentModel, assignment_id)
        return _to_dto(row) if row is not None else None

    async def override_transit_interval(
        self, assignment_id: UUID, *, transit_interval_minutes: int
    ) -> CrewAssignmentDTO:
        row = await self._session.get(CrewAssignmentModel, assignment_id)
        if row is None:
            raise ResourceNotFoundError(f"La asignación {assignment_id} no existe")
        row.transit_interval_minutes = transit_interval_minutes
        row.transit_interval_overridden = True
        await self._session.flush()
        return _to_dto(row)
