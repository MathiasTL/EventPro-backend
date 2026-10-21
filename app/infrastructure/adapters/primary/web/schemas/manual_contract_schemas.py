from datetime import date, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.phone_number import PhoneNumber


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ManualClient(StrictModel):
    phone: str
    full_name: str = Field(min_length=2, max_length=120)
    dni: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    ruc: str | None = Field(default=None, pattern=r"^[0-9]{11}$")

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        try:
            return PhoneNumber.parse(value).value
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc


class ManualExtra(StrictModel):
    extra_id: UUID
    quantity: int = Field(ge=1, le=100)


class ManualAdvance(StrictModel):
    payment_method: str = Field(pattern=r"^(YAPE|PLIN|BANK_TRANSFER|CASH)$")
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    transaction_reference: str | None = Field(default=None, max_length=100)


class ManualContractRequest(StrictModel):
    client: ManualClient
    event_date: date
    event_time: time
    location_address: str = Field(min_length=5, max_length=250)
    location_district: str = Field(min_length=2, max_length=80)
    package_id: UUID
    theme_id: UUID | None = None
    extras: list[ManualExtra] = Field(default_factory=list, max_length=30)
    client_provides_mobility: bool = False
    agreed_services_subtotal: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    agreed_services_reason: str | None = Field(default=None, min_length=10, max_length=500)
    agreed_mobility_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    mobility_override_reason: str | None = Field(default=None, min_length=10, max_length=500)
    advance: ManualAdvance
    client_observations: Annotated[str, StringConstraints(strip_whitespace=False)] | None = Field(
        default=None, max_length=5000
    )
    custom_clauses: Annotated[str, StringConstraints(strip_whitespace=False)] | None = Field(
        default=None, max_length=10000
    )
    issue_contract: bool = True

    @model_validator(mode="after")
    def policies(self) -> "ManualContractRequest":
        if len({extra.extra_id for extra in self.extras}) != len(self.extras):
            raise ValueError("No repitas el mismo extra; indica su cantidad")
        if self.agreed_services_subtotal is not None and not self.agreed_services_reason:
            raise ValueError("El precio acordado requiere motivo")
        if self.client_provides_mobility and self.agreed_mobility_amount not in (None, 0):
            raise ValueError("El transporte del cliente exonera movilidad")
        if self.agreed_mobility_amount is not None and not self.mobility_override_reason:
            raise ValueError("La movilidad acordada requiere motivo")
        return self
