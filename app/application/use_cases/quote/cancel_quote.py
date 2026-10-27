"""Cancelación real de cotizaciones (E1, RN-09).

Solo cancela cotizaciones abiertas y nunca mientras exista un pago en revisión. No confirma
la transacción: el router que la invoca es dueño del ``commit``.
"""

from uuid import UUID

from app.application.dtos.quote_dto import CancelledQuoteDTO
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError, QuoteNotFoundError


class CancelQuoteUseCase:
    """``SENT`` o ``PAYMENT_STARTED`` → ``CANCELLED``; rechaza con un pago en revisión."""

    def __init__(self, quotes: IQuoteRepositoryPort) -> None:
        self._quotes = quotes

    async def execute(self, quote_id: UUID, reason: str | None = None) -> CancelledQuoteDTO:
        quote = await self._quotes.get_by_id_for_update(quote_id)
        if quote is None:
            raise QuoteNotFoundError("La cotización solicitada no existe.")
        if quote.status not in (QuoteStatus.SENT, QuoteStatus.PAYMENT_STARTED):
            raise InvalidQuoteStateError(f"La cotización está {quote.status.value}.")
        if await self._quotes.has_payment_in_review(quote_id):
            raise InvalidQuoteStateError(
                "Hay un pago en verificación: resuélvalo antes de cancelar la cotización."
            )
        quote.cancel(reason)
        await self._quotes.save(quote)
        return CancelledQuoteDTO(quote_id=quote.id, status=quote.status)
