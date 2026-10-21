"""Datos de emisión y consulta del contrato, independientes de HTTP y SQL."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from uuid import UUID

from app.domain.entities.contract import Contract, ContractStatus


@dataclass(frozen=True, kw_only=True)
class ContractData:
    event_id: UUID
    event_status: str
    quote_id: UUID
    source: str
    client_name: str
    phone: str
    dni: str | None
    ruc: str | None
    event_date: date
    start_time: time
    end_time: time
    address: str
    district: str
    package_name: str
    theme_name: str | None
    extras: tuple[str, ...]
    services: Decimal
    mobility: Decimal
    total: Decimal
    advance: Decimal
    required_advance: Decimal
    observations: str | None
    event_started: bool = False


@dataclass(frozen=True)
class ContractFilters:
    status: ContractStatus | None = None
    event_id: UUID | None = None
    is_manual_mode: bool | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class ContractPage:
    items: list[Contract]
    page: int
    page_size: int
    total: int
