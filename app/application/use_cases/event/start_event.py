"""US-17 parcial: verifica saldo y coordina el inicio, sin registrar nuevos pagos."""

from uuid import UUID

from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.dtos.event_start_dto import EventStartDTO
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.ports.output.pre_show_payment_verification_port import (
    IPreShowPaymentVerificationPort,
)
from app.application.use_cases.event.access_errors import (
    EventAccessDeniedError as EventAccessDeniedError,
)
from app.application.use_cases.event.event_operation_access import authorize_event
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class StartEventUseCase:
    def __init__(
        self,
        events: IEventRepositoryPort,
        payments: IPreShowPaymentVerificationPort,
        crews: ICrewScheduleReadPort,
        clock: IClockPort,
    ) -> None:
        self._events = events
        self._payments = payments
        self._crews = crews
        self._clock = clock

    async def execute(self, event_id: UUID, actor: ScheduleActor) -> EventStartDTO:
        await authorize_event(event_id, actor, self._crews, hide_unassigned=False)
        event = await self._events.get_by_id_for_update(event_id)
        if event is None:
            raise ResourceNotFoundError("El evento no existe.")
        event.validate_start_state()
        verified = await self._payments.get_verified_balance_total(event_id)
        event.start(verified_pre_show_amount=verified, started_at=self._clock.utcnow())
        await self._events.save_start(event)
        assert event.actual_start_time is not None
        return EventStartDTO(event.id, event.status, event.actual_start_time)
