from uuid import UUID

from app.application.dtos.event_extension_dto import EventSettlementDTO
from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.use_cases.event.event_operation_access import authorize_event
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.services.financial_reporting import FinancialReportingService


class SettleEventUseCase:
    def __init__(
        self, events: IEventRepositoryPort, crews: ICrewScheduleReadPort, clock: IClockPort
    ) -> None:
        self._events, self._crews, self._clock = events, crews, clock

    async def execute(self, event_id: UUID, actor: ScheduleActor) -> EventSettlementDTO:
        await authorize_event(event_id, actor, self._crews)
        try:
            event = await self._events.get_by_id_for_update(event_id)
            if event is None:
                raise ResourceNotFoundError("El evento no existe.")
            event.validate_operating_state()
            totals = await self._events.get_verified_extension_totals(event_id)
            event.settle(
                verified_extension_amount=totals.amount, verified_extra_minutes=totals.extra_minutes
            )
            costs = await self._events.get_settlement_costs(event_id)
            snapshot = FinancialReportingService.snapshot(
                event, costs, totals.amount, self._clock.utcnow()
            )
            await self._events.save_settlement(event, snapshot)
            return EventSettlementDTO(event.id, event.status)
        except BaseException:
            await self._events.rollback_operation()
            raise
