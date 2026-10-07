"""Persistencia del flujo manual, usando las tablas comerciales existentes."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.application.dtos.catalog_dto import InventoryRequirementDTO
from app.application.use_cases.quote.prepare_budget import BudgetLine, BudgetResult
from app.domain.value_objects.time_window import TimeWindow


@dataclass(frozen=True)
class ManualBooking:
    quote_id: UUID
    client_name: str
    phone: str
    address: str
    district: str
    event_date: date
    start_time: time
    package_id: UUID
    package_name: str
    theme_name: str | None
    duration_minutes: int
    lines: tuple[BudgetLine, ...]
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    payment_id: UUID
    payment_status: str
    paid_amount: Decimal
    evidence_path: str
    quote_status: str
    event_id: UUID | None = None
    contract_id: UUID | None = None
    contract_number: str | None = None
    pdf_path: str | None = None


class IManualBookingStore(Protocol):
    async def get(self, quote_id: UUID, *, lock: bool = False) -> ManualBooking | None: ...

    async def stage(
        self,
        quote_id: UUID,
        budget: BudgetResult,
        phone: str,
        district: str,
        payment_method: str,
        evidence_path: str,
    ) -> ManualBooking: ...

    async def finalize(
        self,
        booking: ManualBooking,
        user_id: UUID,
        event_id: UUID,
        contract_id: UUID,
        contract_number: str,
        pdf_path: str,
        window: TimeWindow,
        requirements: tuple[InventoryRequirementDTO, ...],
    ) -> ManualBooking: ...

    async def list_recent(self) -> tuple[ManualBooking, ...]: ...


class IBookingDocuments(Protocol):
    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str: ...

    async def delete(self, evidence_path: str) -> None: ...
