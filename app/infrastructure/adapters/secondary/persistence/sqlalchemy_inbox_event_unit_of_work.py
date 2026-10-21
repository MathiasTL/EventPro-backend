"""Unidad de trabajo de los eventos de mensaje de la bandeja sobre SQLAlchemy."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.output.inbox_event_unit_of_work_port import InboxEventTransaction
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_client_repository,
    sqlalchemy_conversation_link_repository,
    sqlalchemy_outbox_repository,
)


class SqlAlchemyInboxEventUnitOfWork:
    """Una sesión y una transacción por evento de mensaje: outbox, vínculos y clientes."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> AbstractAsyncContextManager[InboxEventTransaction]:
        return self._open()

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[InboxEventTransaction]:
        async with self._session_factory() as session, session.begin():
            yield InboxEventTransaction(
                outbox=sqlalchemy_outbox_repository.SqlAlchemyOutboxRepository(session),
                links=sqlalchemy_conversation_link_repository.SqlAlchemyConversationLinkRepository(
                    session
                ),
                clients=sqlalchemy_client_repository.SqlAlchemyClientRepository(session),
            )
