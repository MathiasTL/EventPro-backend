from typing import Protocol


class IPaymentEvidenceStoragePort(Protocol):
    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str:
        """Guarda el comprobante y devuelve su ruta lógica."""

    async def open(self, evidence_path: str) -> bytes:
        """Recupera los bytes del comprobante."""

    def max_bytes(self) -> int:
        """Límite de 5 MB según contrato."""
