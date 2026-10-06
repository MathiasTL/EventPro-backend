"""Almacenamiento local de comprobantes: UUID, extensión neutral, MIME por contenido."""

from pathlib import Path
from uuid import uuid4

import filetype  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.domain.exceptions.resource_exceptions import ValidationError

_MAX_BYTES = 5 * 1024 * 1024
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


class LocalEvidenceStorage:
    def __init__(self, base_path: str | Path | None = None) -> None:
        self._base = Path(base_path or get_settings().local_storage_path)
        self._dir = self._base / "evidence"
        self._dir.mkdir(parents=True, exist_ok=True)

    def max_bytes(self) -> int:
        return _MAX_BYTES

    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str:
        if len(data) > _MAX_BYTES:
            raise ValidationError("El archivo no puede superar 5 MB")
        kind = filetype.guess(data)
        detected = kind.mime if kind is not None else ""
        if detected not in _ALLOWED_MIME:
            raise ValidationError("Tipo de archivo no permitido; use JPEG, PNG, WebP o PDF")
        ext = _EXT_BY_MIME[detected]
        filename = f"{uuid4()}{ext}"
        path = self._dir / filename
        path.write_bytes(data)
        return str(Path("evidence") / filename)

    async def open(self, evidence_path: str) -> bytes:
        safe = Path(evidence_path)
        if safe.is_absolute() or ".." in safe.parts:
            raise ValidationError("Ruta de evidencia inválida")
        path = (self._base / Path(*safe.parts)).resolve()
        if not path.is_file():
            raise ValidationError("Evidencia no encontrada")
        return path.read_bytes()
