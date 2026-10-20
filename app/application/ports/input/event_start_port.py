from typing import Protocol
from uuid import UUID

from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.dtos.event_start_dto import EventStartDTO


class IStartEventPort(Protocol):
    async def execute(self, event_id: UUID, actor: ScheduleActor) -> EventStartDTO:
        """Inicia un evento autorizado cuyo saldo pre-show esté verificado."""
