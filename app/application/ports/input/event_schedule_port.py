from collections.abc import Sequence
from typing import Protocol

from app.application.dtos.event_schedule_dto import (
    EventScheduleDTO,
    EventScheduleFilters,
    ScheduleActor,
)


class IGetEventSchedulePort(Protocol):
    async def execute(
        self, filters: EventScheduleFilters, actor: ScheduleActor
    ) -> Sequence[EventScheduleDTO]:
        """Consulta el cronograma dentro del alcance autorizado del usuario."""
