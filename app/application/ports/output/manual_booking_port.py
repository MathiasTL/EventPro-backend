"""Persistencia del flujo manual, usando las tablas comerciales existentes."""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.application.dtos.budget_dto import BudgetLine, BudgetResult
from app.application.dtos.catalog_dto import InventoryRequirementDTO
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
    request_hash: str | None = None
    expires_at: datetime | None = None
    registered_by_user_id: UUID | None = None
    mobility_amount: Decimal = Decimal("0.00")
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
        user_id: UUID,
        request_hash: str,
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
        override_reason: str | None = None,
    ) -> ManualBooking: ...

    async def list_recent(
        self, *, page: int = 1, page_size: int = 20
    ) -> tuple[ManualBooking, ...]: ...

    async def lock_request(self, quote_id: UUID) -> None: ...

    async def require_approval(self, booking: ManualBooking, user_id: UUID) -> ManualBooking: ...


class IBookingDocuments(Protocol):
    def max_bytes(self) -> int: ...

    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str: ...

    async def delete(self, evidence_path: str) -> None: ...

    async def open(self, path: str) -> bytes: ...
