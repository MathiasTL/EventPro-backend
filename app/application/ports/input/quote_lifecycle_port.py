from typing import Protocol
from uuid import UUID

from app.application.dtos.quote_dto import CancelledQuoteDTO, PayAdvanceResultDTO


class IPayAdvancePort(Protocol):
    async def execute(self, quote_id: UUID) -> PayAdvanceResultDTO:
        """Revalida disponibilidad si corresponde y pasa a PAYMENT_STARTED (idempotente).

        No confirma la transacción. Lanza ``QuoteNotFoundError``, ``QuoteExpiredError``,
        ``InvalidQuoteStateError``, ``AvailabilityConflictError`` o
        ``SimultaneousThresholdExceededError``; en los dos últimos no revela datos de pago.
        """


class ICancelQuotePort(Protocol):
    async def execute(self, quote_id: UUID, reason: str | None = None) -> CancelledQuoteDTO:
        """SENT o PAYMENT_STARTED pasa a CANCELLED; rechaza si hay un pago en verificación.

        No confirma la transacción. Lanza ``QuoteNotFoundError`` o ``InvalidQuoteStateError``.
        """
