"""Entrada HTTP del contrato de cotización; los DTOs de salida son compartidos."""

from datetime import date, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.application.dtos.quote_dto import ClientInput, CreateQuoteInput, QuoteExtraInput
from app.domain.entities.quote import QuoteSource


class QuoteClientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    phone: str = Field(min_length=1, max_length=30)
    full_name: str = Field(min_length=1, max_length=120)
    dni: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    ruc: str | None = Field(default=None, pattern=r"^[0-9]{11}$")


class QuoteExtraRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extra_id: UUID
    quantity: int = Field(gt=0, strict=True)


class CreateQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    package_id: UUID
    event_date: date
    event_time: time
    location_address: str = Field(min_length=1, max_length=255)
    location_district: str = Field(min_length=1, max_length=80)
    client: QuoteClientRequest | None = None
    client_id: UUID | None = None
    theme_id: UUID | None = None
    extras: list[QuoteExtraRequest] = Field(default_factory=list)
    client_provides_mobility: bool = False
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=7)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=7)
    observations: Annotated[str, StringConstraints(strip_whitespace=False, max_length=5000)] | None = (
        None
    )
    source: QuoteSource = QuoteSource.WHATSAPP

    def to_input(self) -> CreateQuoteInput:
        return CreateQuoteInput(
            **self.model_dump(exclude={"client", "extras"}),
            client=ClientInput(**self.client.model_dump()) if self.client else None,
            extras=tuple(QuoteExtraInput(**e.model_dump()) for e in self.extras),
        )
