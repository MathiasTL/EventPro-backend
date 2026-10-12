"""Lectura de documentos para el despachador del outbox, sobre el almacenamiento existente."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.adapters.secondary.storage.postgres_booking_documents import (
    PostgresBookingDocuments,
)


class StorageDocumentSource:
    """Implementa ``IDocumentSourcePort`` reutilizando ``PostgresBookingDocuments.open``.

    Las rutas ``database/...`` se leen de ``booking_documents``; las demás (contratos y
    comprobantes anteriores) se leen del disco local. Abre una sesión corta por lectura, fuera
    de cualquier transacción del outbox, y no escribe nada.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self, path: str) -> bytes:
        async with self._session_factory() as session:
            return await PostgresBookingDocuments(session).open(path)
