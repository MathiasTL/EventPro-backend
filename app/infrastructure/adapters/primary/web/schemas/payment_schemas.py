"""Esquemas de la API de pagos; únicamente en el adaptador HTTP."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.entities.payment import (
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)

ScheduleAmount = Decimal


class PaymentCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    concept: PaymentConcept
    validation_status: PaymentValidationStatus
    message: str


class PaymentReadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class PaymentPageResponse(BaseModel):
    items: list[PaymentReadResponse]
    page: int
    page_size: int
    total: int


class PaymentVerifyRequest(BaseModel):
    status: Literal["VERIFIED", "REJECTED"]
    rejection_reason: str | None = None
    event_id: UUID | None = None


class PaymentVerifyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    validation_status: PaymentValidationStatus
    rejection_reason: str | None


class PaymentAuditRequest(BaseModel):
    audit_status: PaymentAuditStatus
    audit_notes: str | None = None


class PaymentAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    audit_status: PaymentAuditStatus
    audited_at: datetime


class PaymentRefundRequest(BaseModel):
    refund_method: PaymentMethod
    transaction_reference: str | None = None
    notes: str | None = None


class PaymentRefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    validation_status: PaymentValidationStatus
