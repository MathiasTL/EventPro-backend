"""DTOs de los procesos de control y *overrides* (RF-20, RF-21, RF-22)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domain.entities.payment import PaymentValidationStatus


class OverbookedDecision(StrEnum):
    """Decisión del encargado ante un pago en aprobación manual."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ApproveOverbookedInput:
    """Resolución manual de un pago en ``REQUIRES_MANUAL_APPROVAL``."""

    payment_id: UUID
    decision: OverbookedDecision
    decided_by_user_id: UUID
    notes: str | None = None
    event_id: UUID | None = None


@dataclass(frozen=True)
class ApproveOverbookedDTO:
    """Resultado de la resolución del sobrecupo."""

    payment_id: UUID
    validation_status: PaymentValidationStatus
    event_created_id: UUID | None = None


@dataclass(frozen=True)
class OverrideMobilityInput:
    """RF-21 / US-19: sobrescritura manual del costo de movilidad de una cotización."""

    quote_id: UUID
    manual_mobility_amount: Decimal
    reason: str
    decided_by_user_id: UUID


@dataclass(frozen=True)
class OverrideMobilityDTO:
    """Cotización recalculada tras el override: total y saldo nuevos, adelanto inalterado."""

    quote_id: UUID
    mobility_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    mobility_overridden: bool


@dataclass(frozen=True)
class OverrideTransitIntervalInput:
    """RF-22 / US-20: ajuste manual del intervalo de tránsito de una asignación."""

    assignment_id: UUID
    transit_interval_minutes: int
    reason: str
    decided_by_user_id: UUID


@dataclass(frozen=True)
class OverrideTransitIntervalDTO:
    """Asignación con el intervalo de tránsito sobrescrito."""

    assignment_id: UUID
    transit_interval_minutes: int
    transit_interval_overridden: bool
