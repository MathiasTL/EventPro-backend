from typing import Protocol
from uuid import UUID

from app.domain.value_objects.money import Money


class IPreShowPaymentVerificationPort(Protocol):
    async def get_verified_balance_total(self, event_id: UUID) -> Money:
        """Total BALANCE en VERIFIED, en PEN; no incluye adelantos ni extensiones.

        Debe devolver cero si no hay pagos verificados, nunca asumir pagado.
        """
