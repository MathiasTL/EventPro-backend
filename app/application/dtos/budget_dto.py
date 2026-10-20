"""Datos compartidos del presupuesto; independientes de los casos de uso."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from uuid import UUID

from app.application.dtos.availability_dto import AvailabilityResult


@dataclass(frozen=True)
class BudgetInput:
    client_name: str
    event_date: date
    start_time: time
    address: str
    package_id: UUID
    theme_id: UUID | None
    extra_ids: tuple[UUID, ...]
    client_provides_transport: bool = True
    manual_mobility_amount: Decimal = Decimal("0.00")
    mobility_override_reason: str | None = None


@dataclass(frozen=True)
class BudgetLine:
    name: str
    amount: Decimal


@dataclass(frozen=True)
class BudgetResult:
    request: BudgetInput
    package_name: str
    theme_name: str | None
    duration_minutes: int
    lines: tuple[BudgetLine, ...]
    services_subtotal: Decimal
    mobility_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    availability: AvailabilityResult
