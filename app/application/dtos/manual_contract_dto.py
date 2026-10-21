"""Entrada de contingencia sin dependencias HTTP."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.application.dtos.budget_dto import BudgetInput


@dataclass(frozen=True, kw_only=True)
class ManualContractInput:
    quote_id: UUID
    request_hash: str
    budget: BudgetInput
    phone: str
    district: str
    dni: str | None
    ruc: str | None
    quantities: tuple[tuple[UUID, int], ...]
    agreed_services: Decimal | None
    agreed_reason: str | None
    payment_method: str
    advance: Decimal
    reference: str | None
    observations: str | None
    clauses: str | None
    issue: bool
    receipt: bytes
    receipt_type: str
    receipt_name: str
