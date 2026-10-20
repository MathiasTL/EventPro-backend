"""Repositorio de cotizaciones con SQLAlchemy. No confirma: la transacción es del llamador."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.quote import Quote
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.mappers.quote_mapper import (
    apply_quote_to_model,
    quote_to_domain,
    quote_to_model,
)
from app.infrastructure.adapters.secondary.persistence.models.quote_model import QuoteModel


class SqlAlchemyQuoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, quote: Quote) -> Quote:
        self._session.add(quote_to_model(quote))
        await self._session.flush()
        return quote

    async def save(self, quote: Quote) -> Quote:
        row = await self._session.get(QuoteModel, quote.id)
        if row is None:
            raise ResourceNotFoundError(f"La cotización {quote.id} no existe")
        apply_quote_to_model(row, quote)
        await self._session.flush()
        return quote

    async def get_by_id(self, quote_id: UUID) -> Quote | None:
        row = await self._session.get(QuoteModel, quote_id)
        return quote_to_domain(row) if row is not None else None
