from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import ListQuotesFilter, QuoteListItemDTO
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort


class ListQuotesUseCase:
    def __init__(self, quotes: IQuoteRepositoryPort) -> None:
        self._quotes = quotes

    async def execute(self, filters: ListQuotesFilter) -> PageDTO[QuoteListItemDTO]:
        return await self._quotes.list_quotes(filters)
