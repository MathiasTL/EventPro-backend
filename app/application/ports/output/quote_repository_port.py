from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import ListQuotesFilter, QuoteDetailDTO, QuoteListItemDTO
from app.domain.entities.quote import Quote


class IQuoteRepositoryPort(Protocol):
    """Persistencia de Quote. Nunca confirma (``commit``): la transacción es del llamador."""

    async def add(self, quote: Quote) -> Quote:
        """Inserta una cotización nueva con sus extras; falla si el id o el hash ya existen."""

    async def save(self, quote: Quote) -> Quote:
        """Actualiza una cotización existente; lanza ResourceNotFoundError si no existe.

        Solo persiste el estado y los campos de ciclo de vida; no persiste cambios en ``extras``
        (los extras se escriben una sola vez en ``add``).
        """

    async def get_by_id(self, quote_id: UUID) -> Quote | None:
        """Devuelve la cotización con sus extras, o None."""

    async def get_by_id_for_update(self, quote_id: UUID) -> Quote | None:
        """Como ``get_by_id``, pero bloquea la fila (``FOR UPDATE``) hasta cerrar la transacción."""

    async def get_detail(self, quote_id: UUID) -> QuoteDetailDTO | None:
        """Detalle comercial con importes congelados, cliente y pagos."""

    async def list_quotes(self, filters: ListQuotesFilter) -> PageDTO[QuoteListItemDTO]:
        """Filtra por fecha del evento y ordena por envío e id descendentes."""

    async def find_due(self, now: datetime) -> tuple[Quote, ...]:
        """Bloquea vencibles sin pagos en revisión; omite filas bloqueadas por otro proceso."""

    async def has_payment_in_review(self, quote_id: UUID) -> bool:
        """PENDING_VERIFICATION o REQUIRES_MANUAL_APPROVAL impiden vencer."""
