"""Unidad de trabajo de ``conversation_links`` sobre SQLAlchemy."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.output.conversation_link_repository_port import (
    IConversationLinkRepositoryPort,
)
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_conversation_link_repository,
)


class SqlAlchemyConversationLinkUnitOfWork:
    """Una sesión y una transacción por bloque; revierte si el bloque falla."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> AbstractAsyncContextManager[IConversationLinkRepositoryPort]:
        return self._open()

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[IConversationLinkRepositoryPort]:
        async with self._session_factory() as session, session.begin():
            yield sqlalchemy_conversation_link_repository.SqlAlchemyConversationLinkRepository(
                session
            )
