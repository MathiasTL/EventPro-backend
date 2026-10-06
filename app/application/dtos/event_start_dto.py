from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.value_objects.event_status import EventStatus


@dataclass(frozen=True)
class EventStartDTO:
    event_id: UUID
    status: EventStatus
    actual_start_time: datetime
