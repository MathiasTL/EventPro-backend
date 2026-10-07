"""Esquemas HTTP de procesos de control y *overrides* (RF-20, RF-21, RF-22)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

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
