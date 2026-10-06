"""Contrato del cronograma, independiente de HTTP y de persistencia."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from uuid import UUID

from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.role import Role


@dataclass(frozen=True)
class EventScheduleFilters:
    from_date: date | None = None
    to_date: date | None = None
    status: EventStatus | None = None


@dataclass(frozen=True)
class ScheduleActor:
    user_id: UUID
    role: Role


@dataclass(frozen=True)
class QuoteScheduleDTO:
    client_name: str
    package_name: str
    theme_name: str


@dataclass(frozen=True)
class CrewScheduleDTO:
    crew_id: UUID
    leader_name: str


@dataclass(frozen=True)
class EventScheduleDTO:
    event_id: UUID
    event_code: str
    event_date: date
    start_time: time
    end_time: time
    district: str
    client_name: str
    package_name: str
    theme_name: str
    crews: tuple[CrewScheduleDTO, ...]
    client_observations: str | None
    status: EventStatus
    pending_balance_to_collect: Decimal
