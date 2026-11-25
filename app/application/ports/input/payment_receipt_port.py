from typing import Protocol
from uuid import UUID


class IRegisterPaymentReceiptPort(Protocol):
    async def execute(self, quote_id: UUID, evidence_path: str) -> None:
        """Registra el adelanto de la cotización con el comprobante ya guardado.

        El importe es el adelanto de la cotización y el medio queda sin especificar: el
        encargado lo confirma al verificar. No confirma la transacción. Lanza
        ``QuoteNotFoundError``, ``InvalidQuoteStateError`` si la cotización ya no espera el
        pago o ``ResourceInUseError`` si ya hay un adelanto pendiente o en revisión.
        """
