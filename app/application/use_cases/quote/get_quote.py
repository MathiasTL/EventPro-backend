from uuid import UUID

from app.application.dtos.quote_dto import QuoteDetailDTO
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort
from app.domain.exceptions.quote_exceptions import QuoteNotFoundError


class GetQuoteUseCase:
    def __init__(self, quotes: IQuoteRepositoryPort) -> None:
        self._quotes = quotes

    async def execute(self, quote_id: UUID) -> QuoteDetailDTO:
        detail = await self._quotes.get_detail(quote_id)
        if detail is None:
            raise QuoteNotFoundError("Cotización no encontrada")
        return detail
