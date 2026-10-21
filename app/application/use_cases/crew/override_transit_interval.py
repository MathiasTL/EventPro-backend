"""RF-22 / US-20: ajuste manual del intervalo de tránsito de una asignación existente.

El encargado acorta o extiende la ventana mínima que ``TravelIntervalService`` sugiere
entre dos shows sucesivos de un mismo elenco (RN-05). Solo se admite mientras el evento
no haya empezado ni terminado; cada ajuste se registra en la bitácora.
"""

from __future__ import annotations

from app.application.dtos.override_dto import (
    OverrideTransitIntervalDTO,
    OverrideTransitIntervalInput,
)
from app.application.ports.output.crew_assignment_repository_port import (
    ICrewAssignmentRepositoryPort,
)
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.services.audit_service import AuditService
from app.domain.exceptions.event_exceptions import InvalidEventStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.event_status import EventStatus

# Estados anteriores al inicio real del evento (RF-22: solo se ajusta antes de que empiece).
_OVERRIDABLE_EVENT_STATUSES = frozenset(
    {EventStatus.AWAITING_SIGNATURE, EventStatus.SCHEDULED, EventStatus.AWAITING_BALANCE}
)


class OverrideCrewTransitIntervalUseCase:
    """Sobrescribe el intervalo mínimo de tránsito de una asignación de elenco."""

    def __init__(
        self,
        assignments: ICrewAssignmentRepositoryPort,
        events: IEventRepositoryPort,
        audit: AuditService,
    ) -> None:
        self._assignments = assignments
        self._events = events
        self._audit = audit

    async def execute(self, dto: OverrideTransitIntervalInput) -> OverrideTransitIntervalDTO:
        assignment = await self._assignments.get_by_id(dto.assignment_id)
        if assignment is None:
            raise ResourceNotFoundError("Asignación de elenco no encontrada")

        event = await self._events.get_by_id_for_update(assignment.event_id)
        if event is None:
            raise ResourceNotFoundError("Evento no encontrado")
        if event.status not in _OVERRIDABLE_EVENT_STATUSES:
            raise InvalidEventStateError(
                f"El evento está {event.status.value}: ya empezó o finalizó."
            )

        old_values: dict[str, object] = {
            "transit_interval_minutes": assignment.transit_interval_minutes,
            "transit_interval_overridden": assignment.transit_interval_overridden,
        }
        updated = await self._assignments.override_transit_interval(
            dto.assignment_id, transit_interval_minutes=dto.transit_interval_minutes
        )
        # El override siempre fija un valor; nunca vuelve a quedar en None.
        assert updated.transit_interval_minutes is not None

        await self._audit.record(
            action="OVERRIDE_TRANSIT_INTERVAL",
            entity_name="crew_assignments",
            entity_id=updated.id,
            user_id=dto.decided_by_user_id,
            old_values=old_values,
            new_values={
                "transit_interval_minutes": updated.transit_interval_minutes,
                "transit_interval_overridden": updated.transit_interval_overridden,
                "reason": dto.reason,
            },
        )

        return OverrideTransitIntervalDTO(
            assignment_id=updated.id,
            transit_interval_minutes=updated.transit_interval_minutes,
            transit_interval_overridden=updated.transit_interval_overridden,
        )
