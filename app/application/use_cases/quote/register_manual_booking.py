"""Entrada idempotente: cotización, comprobante y adelanto en una transacción."""

from dataclasses import dataclass
from uuid import UUID

from app.application.dtos.budget_dto import BudgetInput
from app.application.ports.output.manual_booking_port import (
    IBookingDocuments,
    IManualBookingStore,
    ManualBooking,
)
from app.application.use_cases.quote.prepare_budget import PrepareBudgetUseCase
from app.domain.exceptions.resource_exceptions import ResourceInUseError, ValidationError


@dataclass(frozen=True)
class RegisterManualBookingInput:
    quote_id: UUID
    budget: BudgetInput
    phone: str
    district: str
    payment_method: str
    paid_amount: str
    request_hash: str
    receipt: bytes
    content_type: str
    filename: str


class RegisterManualBookingUseCase:
    def __init__(
        self, store: IManualBookingStore, budget: PrepareBudgetUseCase, receipts: IBookingDocuments
    ) -> None:
        self._store, self._budget, self._receipts = store, budget, receipts

    async def execute(
        self, request: RegisterManualBookingInput, user_id: UUID
    ) -> tuple[ManualBooking, bool]:
        # Candado por clave de idempotencia, independiente del candado de capacidad.
        await self._store.lock_request(request.quote_id)
        existing = await self._store.get(request.quote_id)
        if existing is not None:
            if existing.request_hash != request.request_hash:
                raise ResourceInUseError("La referencia ya pertenece a una solicitud diferente")
            return existing, False
        budget = await self._budget.execute(request.budget)
        from decimal import Decimal

        if Decimal(request.paid_amount) != budget.advance_amount:
            raise ValidationError(
                "El importe del comprobante debe coincidir con el adelanto calculado"
            )
        path = await self._receipts.store(
            data=request.receipt,
            content_type=request.content_type,
            original_filename=request.filename,
        )
        booking = await self._store.stage(
            request.quote_id,
            budget,
            request.phone,
            request.district,
            request.payment_method,
            path,
            user_id,
            request.request_hash,
        )
        return booking, True
