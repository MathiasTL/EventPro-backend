"""DTOs del contrato de lectura de clientes (``IFindClientsPort`` e ``IGetClientPort``).

Los nombres y los tipos reproducen los cuerpos de ``GET /clients`` y ``GET /clients/{id}``.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.application.dtos.page_dto import validate_pagination
from app.domain.entities.quote import QuoteStatus


@dataclass(frozen=True)
class FindClientsFilter:
    """Búsqueda por texto (nombre o teléfono) o por teléfono exacto, paginada."""

    q: str | None = None
    phone: str | None = None
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        validate_pagination(self.page, self.page_size)


@dataclass(frozen=True)
class ClientDTO:
    id: UUID
    phone: str
    full_name: str
    dni: str | None
    ruc: str | None
    created_at: datetime


@dataclass(frozen=True)
class ClientQuoteSummaryDTO:
    quote_id: UUID
    event_date: date
    total_amount: Decimal
    status: QuoteStatus


@dataclass(frozen=True)
class ClientDetailDTO:
    id: UUID
    phone: str
    full_name: str
    dni: str | None
    ruc: str | None
    created_at: datetime
    quotes: tuple[ClientQuoteSummaryDTO, ...]
