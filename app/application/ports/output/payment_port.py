"""Puertos de salida del módulo de pagos (E5).

Contratos que implementa la capa de infraestructura (SQLAlchemy, disco local) y
consumen los casos de uso de pagos. Siguen el registro de los puertos de
catálogo/disponibilidad definidos por E3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.application.dtos.payment_dto import (
    PaymentFilterDTO,
    PaymentReadDTO,
)
from app.domain.entities.payment import Payment


class IPaymentRepository(ABC):
    """Persistencia de pagos."""

    @abstractmethod
    async def save(self, payment: Payment) -> Payment:
        """Inserta o actualiza un pago."""

    @abstractmethod
    async def get(self, payment_id: UUID) -> Payment | None:
        """Devuelve un pago por id, o ``None`` si no existe."""

    @abstractmethod
    async def list(self, filters: PaymentFilterDTO) -> Sequence[PaymentReadDTO]:
        """Lista pagos aplicando filtros y paginación."""

    @abstractmethod
    async def count(self, filters: PaymentFilterDTO) -> int:
        """Cuenta pagos que cumplen los filtros."""

    @abstractmethod
    async def find_active_advance(self, quote_id: UUID) -> Payment | None:
        """Devuelve el adelanto vigente de una cotización (no rechazado ni devuelto)."""


class IPaymentEvidenceStorage(ABC):
    """Almacenamiento de comprobantes y evidencias de cobro."""

    @abstractmethod
    async def store(
        self,
        *,
        data: bytes,
        content_type: str,
        original_filename: str,
    ) -> str:
        """Guarda el archivo validado y devuelve su ruta lógica (``evidence_path``)."""

    @abstractmethod
    async def open(self, evidence_path: str) -> bytes:
        """Devuelve el contenido del archivo para servirlo vía API."""

    @abstractmethod
    def max_bytes(self) -> int:
        """Tamaño máximo permitido (5 MB según la spec)."""
