"""DTOs de los procesos de control y *overrides* (RF-20, RF-21, RF-22)."""

from __future__ import annotations

from dataclasses import dataclass
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
