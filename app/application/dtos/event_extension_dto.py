"""Contratos puros para registrar extensiones y liquidar eventos."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.entities.payment import (
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money


@dataclass(frozen=True)
class RegisterEventExtensionInput:
    event_id: UUID
    extra_minutes: int
    agreed_rate: Decimal
    payment_method: PaymentMethod
    evidence_data: bytes
    evidence_content_type: str
    evidence_filename: str
    transaction_reference: str | None = None


@dataclass(frozen=True)
class ExtensionPaymentDTO:
    payment_id: UUID
    concept: PaymentConcept
    amount: Decimal
    validation_status: PaymentValidationStatus
    audit_status: PaymentAuditStatus


@dataclass(frozen=True)
class EventExtensionDTO:
    event_id: UUID
    status: EventStatus
    extension_id: UUID
    payment: ExtensionPaymentDTO


@dataclass(frozen=True)
class EventSettlementDTO:
    event_id: UUID
    status: EventStatus


@dataclass(frozen=True)
class VerifiedExtensionTotals:
    amount: Money
    extra_minutes: int
