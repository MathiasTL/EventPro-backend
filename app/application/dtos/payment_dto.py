"""Contratos de aplicación para pagos (E5)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.entities.payment import (
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)


@dataclass(frozen=True)
class CreateAdvancePaymentInput:
    quote_id: UUID
    payment_method: PaymentMethod
    amount: Decimal
    evidence_path: str
    transaction_reference: str | None = None


@dataclass(frozen=True)
class PaymentCreatedDTO:
    payment_id: UUID
    concept: PaymentConcept
    validation_status: PaymentValidationStatus
    message: str


@dataclass(frozen=True)
class PaymentReadDTO:
    payment_id: UUID
    quote_id: UUID
    concept: PaymentConcept
    payment_method: PaymentMethod
    amount: Decimal
    validation_status: PaymentValidationStatus
    audit_status: PaymentAuditStatus | None
    event_id: UUID | None
    transaction_reference: str | None
    rejection_reason: str | None
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    registered_by_user_id: UUID | None
    audited_by_user_id: UUID | None
    audited_at: datetime | None
    audit_notes: str | None
    created_at: datetime


@dataclass(frozen=True)
class PaymentFilters:
    validation_status: PaymentValidationStatus | None = None
    concept: PaymentConcept | None = None
    audit_status: PaymentAuditStatus | None = None
    quote_id: UUID | None = None
    event_id: UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class PaymentPageDTO:
    items: list[PaymentReadDTO]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class VerifyPaymentInput:
    payment_id: UUID
    action: str  # "VERIFIED" | "REJECTED"
    verified_by_user_id: UUID
    event_id: UUID | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True)
class VerifyPaymentDTO:
    payment_id: UUID
    validation_status: PaymentValidationStatus
    rejection_reason: str | None


@dataclass(frozen=True)
class AuditPaymentInput:
    payment_id: UUID
    audited_by_user_id: UUID
    audit_status: PaymentAuditStatus
    audit_notes: str | None = None


@dataclass(frozen=True)
class AuditPaymentDTO:
    payment_id: UUID
    audit_status: PaymentAuditStatus
    audited_at: datetime


@dataclass(frozen=True)
class RefundPaymentDTO:
    payment_id: UUID
    validation_status: PaymentValidationStatus
