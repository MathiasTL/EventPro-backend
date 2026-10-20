from typing import Protocol
from uuid import UUID

from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import ListQuotesFilter, QuoteDetailDTO, QuoteListItemDTO


class IGetQuotePort(Protocol):
    async def execute(self, quote_id: UUID) -> QuoteDetailDTO:
        """Detalle con desglose, extras congelados y pagos; lanza ``QuoteNotFoundError``."""


class IListQuotesPort(Protocol):
    async def execute(self, filters: ListQuotesFilter) -> PageDTO[QuoteListItemDTO]:
        """Lista paginada con filtros; la más reciente primero."""
