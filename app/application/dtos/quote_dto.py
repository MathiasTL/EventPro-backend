"""DTOs del contrato de casos de uso de cotización (spec 08, sección 2.2).

Las salidas reproducen los nombres y los tipos de ``POST /quotes``, ``GET /quotes``,
``GET /quotes/{id}`` y ``POST /quotes/{id}/pay-advance``, de modo que el router solo serializa.
Los importes son ``Decimal``; las fechas de ciclo de vida llevan zona horaria UTC;
``event_date`` y ``event_time`` son la hora local del evento, sin zona.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from app.application.dtos.availability_dto import AvailabilityStatus
from app.application.dtos.page_dto import validate_pagination
from app.domain.entities.payment import PaymentConcept, PaymentValidationStatus
from app.domain.entities.quote import QuoteSource, QuoteStatus
from app.domain.exceptions.resource_exceptions import ValidationError

# --- Entradas ---


@dataclass(frozen=True)
class ClientInput:
    """Datos del cliente; si ya existe por teléfono no se sobrescribe su nombre."""

    phone: str
    full_name: str
    dni: str | None = None
    ruc: str | None = None


@dataclass(frozen=True)
class QuoteExtraInput:
    extra_id: UUID
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValidationError("La cantidad de un extra debe ser mayor que cero.")


@dataclass(frozen=True)
class CreateQuoteInput:
    """Entrada de ``ICreateQuotePort``: exactamente uno entre ``client`` y ``client_id``."""

    package_id: UUID
    event_date: date
    event_time: time
    location_address: str
    location_district: str
    client: ClientInput | None = None
    client_id: UUID | None = None
    theme_id: UUID | None = None
    extras: tuple[QuoteExtraInput, ...] = ()
    client_provides_mobility: bool = False
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    observations: str | None = None
    source: QuoteSource = QuoteSource.WHATSAPP

    def __post_init__(self) -> None:
        if (self.client is None) == (self.client_id is None):
            raise ValidationError("Debe indicar exactamente uno entre client y client_id.")


@dataclass(frozen=True)
class ListQuotesFilter:
    """Filtros de ``IListQuotesPort``; el rango filtra por ``event_date``."""

    status: QuoteStatus | None = None
    client_id: UUID | None = None
    from_date: date | None = None
    to_date: date | None = None
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if (
            self.from_date is not None
            and self.to_date is not None
            and self.from_date > self.to_date
        ):
            raise ValidationError("from_date no puede ser posterior a to_date.")
        validate_pagination(self.page, self.page_size)


# --- Salidas ---


@dataclass(frozen=True)
class QuoteBreakdownDTO:
    services_balance_due: Decimal
    mobility_due: Decimal


@dataclass(frozen=True)
class CreatedQuoteDTO:
    quote_id: UUID
    client_id: UUID
    source: QuoteSource
    availability: AvailabilityStatus
    services_subtotal: Decimal
    calculated_distance_km: Decimal | None
    calculated_transit_minutes: int | None
    final_mobility_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    breakdown: QuoteBreakdownDTO
    status: QuoteStatus
    sent_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class ClientSummaryDTO:
    id: UUID
    full_name: str
    phone: str


@dataclass(frozen=True)
class QuoteListItemDTO:
    quote_id: UUID
    client: ClientSummaryDTO
    event_date: date
    package_name: str
    total_amount: Decimal
    status: QuoteStatus
    expires_at: datetime


@dataclass(frozen=True)
class QuotePackageDTO:
    id: UUID
    name: str
    base_price: Decimal


@dataclass(frozen=True)
class QuoteThemeDTO:
    id: UUID
    name: str


@dataclass(frozen=True)
class QuoteExtraDetailDTO:
    extra_id: UUID
    name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class QuotePaymentDTO:
    payment_id: UUID
    concept: PaymentConcept
    validation_status: PaymentValidationStatus


@dataclass(frozen=True)
class QuoteDetailDTO:
    quote_id: UUID
    client: ClientSummaryDTO
    source: QuoteSource
    event_date: date
    event_time: time
    location_address: str
    location_district: str
    package: QuotePackageDTO
    theme: QuoteThemeDTO | None
    extras: tuple[QuoteExtraDetailDTO, ...]
    services_subtotal: Decimal
    final_mobility_amount: Decimal
    mobility_overridden: bool
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    status: QuoteStatus
    sent_at: datetime
    expires_at: datetime
    observations: str | None
    payments: tuple[QuotePaymentDTO, ...]
    event_id: UUID | None


@dataclass(frozen=True)
class WalletInstructionDTO:
    phone: str
    holder: str


@dataclass(frozen=True)
class BankTransferInstructionDTO:
    bank: str
    account: str
    cci: str
    holder: str


@dataclass(frozen=True)
class PaymentInstructionsDTO:
    yape: WalletInstructionDTO
    plin: WalletInstructionDTO
    bank_transfer: BankTransferInstructionDTO


@dataclass(frozen=True)
class PayAdvanceResultDTO:
    quote_id: UUID
    status: QuoteStatus
    availability: AvailabilityStatus
    rechecked: bool
    advance_amount: Decimal
    payment_deadline: datetime
    payment_instructions: PaymentInstructionsDTO


@dataclass(frozen=True)
class CancelledQuoteDTO:
    quote_id: UUID
    status: QuoteStatus
