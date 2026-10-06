from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.application.dtos.payment_dto import PaymentFilters
from app.domain.entities.payment import Payment


class IPaymentRepositoryPort(Protocol):
    async def save(self, payment: Payment) -> Payment:
        """Inserta o actualiza el agregado Payment."""

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        """Devuelve el pago o None."""

    async def list_for_payment(self, filters: PaymentFilters) -> Sequence[Payment]:
        """Pagos del bandeja de verificación/auditoría."""

    async def count_for_payment(self, filters: PaymentFilters) -> int:
        """Total de pagos que cumplen los filtros."""

    async def find_active_advance(self, quote_id: UUID) -> Payment | None:
        """Adelanto en verificación, pendiente de aprobación manual o refund pendiente."""
