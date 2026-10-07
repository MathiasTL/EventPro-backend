from typing import Protocol


class IPaymentEvidenceStoragePort(Protocol):
    async def delete(self, evidence_path: str) -> None:
        """Elimina un comprobante nuevo después de una persistencia fallida."""

    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str:
        """Guarda y devuelve la ruta; rechazos de archivo: EvidenceValidationError neutral."""

    async def open(self, evidence_path: str) -> bytes:
        """Recupera los bytes del comprobante."""

    def max_bytes(self) -> int:
        """Límite de 5 MB según contrato."""
