from typing import Protocol

from app.application.dtos.quote_dto import CreatedQuoteDTO, CreateQuoteInput


class ICreateQuotePort(Protocol):
    async def execute(self, dto: CreateQuoteInput) -> CreatedQuoteDTO:
        """Obtiene o crea el cliente, verifica disponibilidad y crea la cotización en SENT.

        No confirma la transacción ni envía mensajes: el llamador es dueño de ambas cosas.
        Lanza ``AvailabilityConflictError``, ``SimultaneousThresholdExceededError``,
        ``ClientNotFoundError`` (``client_id`` desconocido) o ``ValidationError``.
        """
