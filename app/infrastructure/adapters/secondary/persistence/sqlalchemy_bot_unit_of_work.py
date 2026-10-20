"""Unidad de trabajo del bot sobre SQLAlchemy: una sesión y una transacción por turno."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.output.bot_unit_of_work_port import BotTransaction

BotTransactionBuilder = Callable[[AsyncSession], BotTransaction]


class SqlAlchemyBotUnitOfWork:
    """Abre una sesión, arma con ella los casos de uso del bot y confirma al salir sin error.

    ``build`` recibe la sesión y devuelve los casos de uso que deben compartirla; vive en
    ``containers.py``, donde cada responsable cambia su pieza de ``Fake...`` a la real.
    Si el bloque falla, la transacción se revierte y la excepción sigue su camino.
    """

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], build: BotTransactionBuilder
    ) -> None:
        self._session_factory = session_factory
        self._build = build

    def __call__(self) -> AbstractAsyncContextManager[BotTransaction]:
        return self._open()

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[BotTransaction]:
        async with self._session_factory() as session, session.begin():
            yield self._build(session)
