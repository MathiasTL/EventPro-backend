"""Almacenamiento local de evidencias de pago (E5).

Valida MIME real con ``filetype``, renombra a UUID neutral (nunca se expone la
ruta del SO) y limita el tamaño a 5 MB según la spec de ``/payments/advance``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import filetype

from app.application.ports.output.payment_port import IPaymentEvidenceStorage
from app.core.config import settings
from app.domain.exceptions.resource_exceptions import ValidationError

_MAX_BYTES = 5 * 1024 * 1024
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


class LocalPaymentEvidenceStorage(IPaymentEvidenceStorage):
    """Guarda evidencias en ``LOCAL_STORAGE_PATH/evidence/``."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        base = Path(base_path or settings.local_storage_path)
        self._dir = base / "evidence"
        self._dir.mkdir(parents=True, exist_ok=True)

    def max_bytes(self) -> int:
        return _MAX_BYTES

    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str:
        if len(data) > _MAX_BYTES:
            raise ValidationError("El archivo no puede superar 5 MB")
        kind = filetype.guess(data)
        detected = kind.mime if kind is not None else ""
        if detected not in _ALLOWED_MIME:
            raise ValidationError(
                f"Tipo de archivo no permitido: {detected or 'desconocido'}. "
                "Se aceptan JPEG, PNG, WebP o PDF."
            )
        if content_type and content_type not in _ALLOWED_MIME and detected not in _ALLOWED_MIME:
            raise ValidationError("El content-type no coincide con el archivo")
        ext = _EXT_BY_MIME[detected]
        filename = f"{uuid.uuid4()}{ext}"
        path = self._dir / filename
        path.write_bytes(data)
        return str(Path("evidence") / filename)

    async def open(self, evidence_path: str) -> bytes:
        safe = Path(evidence_path)
        if safe.is_absolute() or ".." in safe.parts:
            raise ValidationError("Ruta de evidencia inválida")
        path = Path(settings.local_storage_path).joinpath(*Path(evidence_path).parts)
        if not path.is_file():
            raise ValidationError("Evidencia no encontrada")
        return path.read_bytes()
