"""Esquemas Pydantic v2 del cronograma; únicamente en el adaptador HTTP."""

from datetime import date, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.domain.value_objects.event_status import EventStatus

ScheduleTime = Annotated[time, PlainSerializer(lambda value: value.strftime("%H:%M"), str)]
ScheduleAmount = Annotated[
    Decimal,
    Field(ge=0, max_digits=10, decimal_places=2),
    PlainSerializer(lambda value: float(value), float, when_used="json"),
]


class CrewScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    crew_id: UUID
    leader_name: str


class EventScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    event_code: str
    event_date: date
    start_time: ScheduleTime
    end_time: ScheduleTime
    district: str
    client_name: str
    package_name: str
    theme_name: str
    crews: list[CrewScheduleResponse]
    client_observations: str | None
    status: EventStatus
    pending_balance_to_collect: ScheduleAmount
