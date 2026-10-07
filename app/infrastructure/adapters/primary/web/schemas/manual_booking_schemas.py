"""Contratos HTTP del presupuesto y reserva manual."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.application.dtos.availability_dto import AvailabilityStatus
from app.domain.entities.payment import PaymentMethod


class BudgetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_name: str = Field(min_length=2, max_length=120)
    event_date: date
    start_time: time
    address: str = Field(min_length=5, max_length=250)
    package_id: UUID
    theme_id: UUID | None = None
    extra_ids: list[UUID] = Field(default_factory=list, max_length=30)
    client_provides_transport: bool
    manual_mobility_amount: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2
    )
    mobility_override_reason: str | None = Field(default=None, min_length=10, max_length=500)

    @model_validator(mode="after")
    def mobility_policy(self) -> "BudgetRequest":
        if self.client_provides_transport and self.manual_mobility_amount != 0:
            raise ValueError("El transporte del cliente exonera movilidad")
        if not self.client_provides_transport and (
            self.manual_mobility_amount <= 0 or not self.mobility_override_reason
        ):
            raise ValueError("Indica un importe manual de movilidad y su motivo")
        return self


class BudgetLineResponse(BaseModel):
    name: str
    amount: Decimal


class BudgetResponse(BaseModel):
    budget_id: UUID
    generated_at: datetime
    package_name: str
    theme_name: str | None
    duration_minutes: int
    lines: list[BudgetLineResponse]
    services_subtotal: Decimal
    mobility_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    availability_status: AvailabilityStatus
    simultaneous_count: int
    pdf_base64: str


class ManualRequest(BudgetRequest):
    quote_id: UUID
    phone: str = Field(pattern=r"^\+?[0-9]{9,15}$")

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = value.lstrip("+")
        if len(digits) == 9:
            digits = "51" + digits
        return "+" + digits

    district: str = Field(min_length=2, max_length=80)
    payment_method: PaymentMethod
    paid_amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_verified: bool
    approve_overbooking: bool = False
    override_reason: str | None = Field(default=None, min_length=10, max_length=500)


class BookingResponse(BaseModel):
    quote_id: UUID
    client_name: str
    phone: str
    address: str
    district: str
    event_date: date
    start_time: time
    package_name: str
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    payment_id: UUID
    payment_status: str
    quote_status: str
    event_id: UUID | None
    contract_id: UUID | None
    contract_number: str | None
