"""Consulta del cronograma (US-16), sin dependencias de infraestructura."""

from collections.abc import Sequence

from app.application.dtos.event_schedule_dto import (
    EventScheduleDTO,
    EventScheduleFilters,
    ScheduleActor,
)
from app.application.ports.output.crew_schedule_read_port import ICrewScheduleReadPort
from app.application.ports.output.event_repository_port import IEventRepositoryPort
from app.application.ports.output.quote_schedule_read_port import IQuoteScheduleReadPort
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.role import Role


class ScheduleAssignmentRequiredError(PermissionError):
    """El operador no tiene una asignación que habilite la consulta."""

    def __init__(self) -> None:
        super().__init__("El operador requiere una asignación activa para consultar el cronograma.")


class GetEventScheduleUseCase:
    def __init__(
        self,
        events: IEventRepositoryPort,
        quotes: IQuoteScheduleReadPort,
        crews: ICrewScheduleReadPort,
    ) -> None:
        self._events = events
        self._quotes = quotes
        self._crews = crews

    async def execute(
        self, filters: EventScheduleFilters, actor: ScheduleActor
    ) -> Sequence[EventScheduleDTO]:
        if (
            filters.from_date is not None
            and filters.to_date is not None
            and filters.from_date > filters.to_date
        ):
            raise ValidationError("from_date no puede ser posterior a to_date")
        event_ids = None
        if actor.role is Role.OPERADOR:
            event_ids = await self._crews.get_assigned_event_ids(actor.user_id)
            if not event_ids:
                raise ScheduleAssignmentRequiredError
        events = await self._events.list_for_schedule(filters, event_ids=event_ids)
        if not events:
            return ()
        quotes = await self._quotes.get_details(frozenset(event.quote_id for event in events))
        crews = await self._crews.get_crews(frozenset(event.id for event in events))
        return tuple(
            EventScheduleDTO(
                event_id=event.id,
                event_code=event.event_code,
                event_date=event.event_date,
                start_time=event.start_time,
                end_time=event.end_time,
                district=event.district,
                client_name=quotes[event.quote_id].client_name,
                package_name=quotes[event.quote_id].package_name,
                theme_name=quotes[event.quote_id].theme_name,
                crews=crews.get(event.id, ()),
                client_observations=event.client_observations,
                status=event.status,
                pending_balance_to_collect=event.pending_balance_to_collect.amount,
            )
            for event in events
        )
