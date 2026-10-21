"""Consultas por lote de la bandeja con SQLAlchemy (spec 09, 5.4). Solo lectura.

Abre una sesión corta por consulta, así sirve tanto a la API como al *worker*.
"""

from collections.abc import Collection, Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities.quote import QuoteStatus
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel
from app.infrastructure.adapters.secondary.persistence.models.quote_model import QuoteModel
from app.infrastructure.adapters.secondary.persistence.models.user import User


class SqlAlchemyInboxLookup:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def client_names(self, client_ids: Collection[UUID]) -> Mapping[UUID, str]:
        return await self._pairs(ClientModel.id, ClientModel.full_name, client_ids)

    async def user_names(self, user_ids: Collection[UUID]) -> Mapping[UUID, str]:
        return await self._pairs(User.id, User.full_name, user_ids)

    async def quote_statuses(self, quote_ids: Collection[UUID]) -> Mapping[UUID, QuoteStatus]:
        found = await self._pairs(QuoteModel.id, QuoteModel.status, quote_ids)
        return {quote_id: QuoteStatus(status) for quote_id, status in found.items()}

    async def _pairs(self, key: Any, value: Any, ids: Collection[UUID]) -> dict[UUID, Any]:
        if not ids:
            return {}
        async with self._session_factory() as session:
            rows = await session.execute(select(key, value).where(key.in_(ids)))
            return {row[0]: row[1] for row in rows}
