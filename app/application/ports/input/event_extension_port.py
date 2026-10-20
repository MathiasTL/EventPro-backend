from typing import Protocol
from uuid import UUID

from app.application.dtos.event_extension_dto import (
    EventExtensionDTO,
    EventSettlementDTO,
    RegisterEventExtensionInput,
)
from app.application.dtos.event_schedule_dto import ScheduleActor


class IRegisterEventExtensionPort(Protocol):
    async def execute(
        self, dto: RegisterEventExtensionInput, actor: ScheduleActor
    ) -> EventExtensionDTO: ...


class ISettleEventPort(Protocol):
    async def execute(self, event_id: UUID, actor: ScheduleActor) -> EventSettlementDTO: ...
