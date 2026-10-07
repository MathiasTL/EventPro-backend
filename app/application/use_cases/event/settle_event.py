from uuid import UUID

from app.application.dtos.event_extension_dto import EventSettlementDTO
from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.use_cases.event.event_operation_access import authorize_event
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class SettleEventUseCase:
    def __init__(self, events: IEventRepositoryPort, crews: ICrewScheduleReadPort) -> None:
        self._events, self._crews = events, crews

    async def execute(self, event_id: UUID, actor: ScheduleActor) -> EventSettlementDTO:
        await authorize_event(event_id, actor, self._crews)
        event = await self._events.get_by_id_for_update(event_id)
        if event is None:
            raise ResourceNotFoundError("El evento no existe.")
        event.validate_operating_state()
        totals = await self._events.get_verified_extension_totals(event_id)
        event.settle(
            verified_extension_amount=totals.amount, verified_extra_minutes=totals.extra_minutes
        )
        await self._events.save_settlement(event)
        return EventSettlementDTO(event.id, event.status)
