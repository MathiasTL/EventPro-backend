"""Esquemas HTTP de procesos de control y *overrides* (RF-20, RF-21, RF-22)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.override_dto import OverbookedDecision
from app.domain.entities.payment import PaymentValidationStatus


class OverbookedDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: OverbookedDecision
    notes: str | None = None
    event_id: UUID | None = None


class OverbookedDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    validation_status: PaymentValidationStatus
    event_created_id: UUID | None = None


class MobilityOverrideRequest(BaseModel):
    """RF-21 / US-19: nuevo monto de movilidad y su justificación."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    manual_mobility_amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)


class MobilityOverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote_id: UUID
    mobility_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    mobility_overridden: bool


class TransitIntervalOverrideRequest(BaseModel):
    """RF-22 / US-20: nuevo intervalo de tránsito y su justificación."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    transit_interval_minutes: int = Field(ge=0, le=1440)
    reason: str = Field(min_length=1, max_length=500)


class TransitIntervalOverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: UUID
    transit_interval_minutes: int
    transit_interval_overridden: bool
