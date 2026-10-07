"""Esquemas Pydantic v2 del cronograma; únicamente en el adaptador HTTP."""

from datetime import date, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import UploadFile
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer

from app.domain.entities.payment import (
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.value_objects.event_status import EventStatus

ScheduleTime = Annotated[time, PlainSerializer(lambda value: value.strftime("%H:%M"), str)]
ScheduleAmount = Annotated[
    Decimal,
    Field(ge=0, max_digits=10, decimal_places=2),
    PlainSerializer(lambda value: float(value), float, when_used="json"),
]


class CrewScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    crew_id: UUID
    leader_name: str


class EventScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    event_code: str
    event_date: date
    start_time: ScheduleTime
    end_time: ScheduleTime
    end_date: date
    district: str
    client_name: str
    package_name: str
    theme_name: str
    crews: list[CrewScheduleResponse]
    client_observations: str | None
    status: EventStatus
    pending_balance_to_collect: ScheduleAmount


class StartEventRequest(BaseModel):
    """Inicio sin datos del cliente: el pago y la hora se obtienen de puertos."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class StartEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    status: EventStatus
    actual_start_time: AwareDatetime


class EventExtensionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extra_minutes: int = Field(gt=0, le=2147483647)
    agreed_rate: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    payment_method: PaymentMethod
    transaction_reference: str | None = Field(default=None, min_length=1, max_length=60)
    evidence_file: UploadFile


class ExtensionPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    concept: PaymentConcept
    amount: ScheduleAmount
    validation_status: PaymentValidationStatus
    audit_status: PaymentAuditStatus


class EventExtensionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    status: EventStatus
    extension_id: UUID
    payment: ExtensionPaymentResponse


class SettleEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SettleEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    status: EventStatus
