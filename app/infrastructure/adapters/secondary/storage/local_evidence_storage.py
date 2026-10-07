"""Almacenamiento local de comprobantes: UUID, extensión neutral, MIME por contenido."""

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

import filetype  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.exceptions.storage_exceptions import EvidenceValidationError

_MAX_BYTES = 5 * 1024 * 1024
logger = logging.getLogger(__name__)
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


class LocalEvidenceStorage:
    def __init__(
        self, base_path: str | Path | None = None, *, allowed_mime: set[str] | None = None
    ) -> None:
        self._base = Path(base_path or get_settings().local_storage_path)
        self._dir = self._base / "evidence"
        self._allowed_mime = _ALLOWED_MIME if allowed_mime is None else allowed_mime

    def max_bytes(self) -> int:
        return _MAX_BYTES

    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str:
        writer = asyncio.create_task(asyncio.to_thread(self._store, data))
        try:
            return await asyncio.shield(writer)
        except asyncio.CancelledError:
            # El hilo no se cancela: esperar su resultado permite compensar el archivo.
            try:
                path = await writer
                await self.delete(path)
            except Exception:
                logger.exception("No se pudo compensar una escritura de evidencia cancelada.")
            raise

    def _store(self, data: bytes) -> str:
        if len(data) > _MAX_BYTES:
            raise EvidenceValidationError("El archivo no puede superar 5 MiB")
        kind = filetype.guess(data)
        detected = kind.mime if kind is not None else ""
        if detected not in self._allowed_mime:
            formats = (
                "JPEG, PNG, WebP o PDF"
                if "application/pdf" in self._allowed_mime
                else "JPEG, PNG o WebP"
            )
            raise EvidenceValidationError(f"Tipo de archivo no permitido; use {formats}")
        ext = _EXT_BY_MIME[detected]
        filename = f"{uuid4()}{ext}"
        path = self._dir / filename
        self._dir.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(data)
        except OSError:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("No se pudo eliminar una evidencia escrita parcialmente.")
            raise
        return str(Path("evidence") / filename)

    async def open(self, evidence_path: str) -> bytes:
        return await asyncio.to_thread(self._open, evidence_path)

    def _open(self, evidence_path: str) -> bytes:
        safe = Path(evidence_path)
        if safe.is_absolute() or ".." in safe.parts:
            raise ValidationError("Ruta de evidencia inválida")
        path = (self._base / Path(*safe.parts)).resolve()
        if not path.is_file():
            raise ValidationError("Evidencia no encontrada")
        return path.read_bytes()

    async def delete(self, evidence_path: str) -> None:
        await asyncio.to_thread(self._delete, evidence_path)

    def _delete(self, evidence_path: str) -> None:
        safe = Path(evidence_path.replace("\\", "/"))
        if (
            safe.is_absolute()
            or ".." in safe.parts
            or not safe.parts
            or safe.parts[0] != "evidence"
        ):
            raise ValidationError("Ruta de evidencia inválida")
        path = (self._base / safe).resolve()
        if not path.is_relative_to(self._dir.resolve()):
            raise ValidationError("Ruta de evidencia inválida")
        path.unlink(missing_ok=True)
