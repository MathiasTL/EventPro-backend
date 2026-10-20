from typing import Protocol


class IExpireDueQuotesPort(Protocol):
    async def execute(self) -> int:
        """Vence las cotizaciones con plazo cumplido y devuelve cuántas venció (RN-09).

        Es idempotente y omite las cotizaciones con un pago en verificación.
        """
