"""Resolución del adelanto sin reserva; el reembolso bancario lo confirma un encargado."""

from uuid import UUID

from app.application.ports.output.manual_booking_port import IManualBookingStore, ManualBooking
from app.domain.exceptions.resource_exceptions import ValidationError


class RefundManualBookingUseCase:
    def __init__(self, store: IManualBookingStore) -> None:
        self._store = store

    async def execute(
        self, quote_id: UUID, user_id: UUID, *, confirm: bool, reason: str
    ) -> ManualBooking:
        if len(reason.strip()) < 10:
            raise ValidationError("Documenta el motivo o referencia de devolución")
        return await self._store.refund(quote_id, user_id, confirm=confirm, reason=reason.strip())
