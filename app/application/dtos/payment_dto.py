"""DTOs del módulo de pagos (E5): RF-11, RF-12, US-11, US-12.

Contratos de entrada/salida para los puertos de pagos y los casos de uso de
registro, verificación, auditoría y reembolso de comprobantes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.entities.payment import (
    AuditStatus,
    PaymentConcept,
    PaymentMethod,
    ValidationStatus,
)


@dataclass(frozen=True)
class CreateAdvancePaymentDTO:
    """Datos para registrar la captura del adelanto asociado a una cotización."""

    quote_id: UUID
    payment_method: PaymentMethod
    amount: Decimal
    evidence_path: str
    transaction_reference: str | None = None


@dataclass(frozen=True)
class AdvancePaymentCreatedDTO:
    """Resultado del registro del comprobante de adelanto (US-11)."""

    payment_id: UUID
    quote_id: UUID
    concept: PaymentConcept
    validation_status: ValidationStatus
    message: str


@dataclass(frozen=True)
class PaymentReadDTO:
    """Vista de un pago para listados y detalle."""

    payment_id: UUID
    quote_id: UUID
    concept: PaymentConcept
    payment_method: PaymentMethod
    amount: Decimal
    validation_status: ValidationStatus
    event_id: UUID | None = None
    audit_status: AuditStatus | None = None
    transaction_reference: str | None = None
    rejection_reason: str | None = None
    verified_by_user_id: UUID | None = None
    registered_by_user_id: UUID | None = None
    audited_by_user_id: UUID | None = None
    audited_at: datetime | None = None
    audit_notes: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class PaymentFilterDTO:
    """Filtros de la bandeja de verificación/auditoría del encargado."""

    validation_status: ValidationStatus | None = None
    concept: PaymentConcept | None = None
    audit_status: AuditStatus | None = None
    quote_id: UUID | None = None
    event_id: UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class PaymentPageDTO:
    """Página de pagos."""

    items: tuple[PaymentReadDTO, ...] = ()
    page: int = 1
    page_size: int = 20
    total: int = 0


@dataclass(frozen=True)
class VerifyPaymentDTO:
    """Decisión del encargado sobre el comprobante de un adelanto (US-12)."""

    status: ValidationStatus  # VERIFIED o REJECTED
    rejection_reason: str | None = None


@dataclass(frozen=True)
class PaymentVerifiedDTO:
    """Resultado de aprobar/rechazar un comprobante."""

    payment_id: UUID
    validation_status: ValidationStatus
    event_created_id: UUID | None = None
    contract_status: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AuditPaymentDTO:
    """Auditoría posterior de un cobro in situ (BALANCE/EXTENSION)."""

    audit_status: AuditStatus  # REVIEWED o FLAGGED
    audit_notes: str | None = None


@dataclass(frozen=True)
class RefundPaymentDTO:
    """Confirmación de devolución de un adelanto."""

    refund_method: PaymentMethod
    transaction_reference: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class RegisterBalancePaymentDTO:
    """Cobro in situ de saldo o extensión, nace VERIFIED (US-17/E6, usado desde E5)."""

    quote_id: UUID
    event_id: UUID
    concept: PaymentConcept  # BALANCE o EXTENSION
    payment_method: PaymentMethod
    amount: Decimal
    evidence_path: str
    registered_by_user_id: UUID
    transaction_reference: str | None = None
