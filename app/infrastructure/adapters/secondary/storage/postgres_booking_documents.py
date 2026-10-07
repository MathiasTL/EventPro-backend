"""Archivos privados compartidos; datos y documento se confirman juntos en PostgreSQL."""

from uuid import UUID, uuid4

import filetype  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.exceptions.storage_exceptions import EvidenceValidationError
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)


class PostgresBookingDocuments:
    def __init__(self, session: AsyncSession, *, purpose: str = "contracts") -> None:
        self._session = session
        self._purpose = purpose

    def max_bytes(self) -> int:
        return 5 * 1024 * 1024

    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str:
        kind = filetype.guess(data)
        allowed = (
            {"application/pdf"}
            if self._purpose in {"contracts", "budgets"}
            else {"application/pdf", "image/jpeg", "image/png", "image/webp"}
        )
        if not data or len(data) > self.max_bytes() or kind is None or kind.mime not in allowed:
            raise EvidenceValidationError("Archivo inválido; máximo 5 MiB y formato autorizado")
        identifier = (
            UUID(original_filename.removesuffix(".pdf")) if self._purpose == "budgets" else uuid4()
        )
        path = f"database/{self._purpose}/{identifier}"
        await self._session.execute(
            text(
                "INSERT INTO booking_documents(path, content, content_type) "
                "VALUES (:path,:data,:mime)"
            ),
            {"path": path, "data": data, "mime": kind.mime},
        )
        return path

    async def open(self, path: str) -> bytes:
        if not path.startswith("database/"):
            # Compatibilidad con contratos/comprobantes anteriores; no migra datos ajenos.
            return await LocalEvidenceStorage().open(path)
        value = await self._session.scalar(
            text("SELECT content FROM booking_documents WHERE path=:path"), {"path": path}
        )
        if value is None:
            raise ResourceNotFoundError("Documento no encontrado")
        return bytes(value)

    async def delete(self, evidence_path: str) -> None:
        await self._session.execute(
            text("DELETE FROM booking_documents WHERE path=:path"), {"path": evidence_path}
        )
