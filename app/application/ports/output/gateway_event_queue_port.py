from datetime import datetime
from typing import Protocol


class IGatewayEventQueuePort(Protocol):
    """Cola de trabajo donde espera un evento del gateway hasta que lo procesa el worker."""

    async def enqueue(self, *, event_id: str, raw_body: bytes, received_at: datetime) -> None:
        """Encola el evento con su cuerpo crudo y la hora firmada de recepción.

        Es idempotente por ``event_id``. Lanza la excepción de la infraestructura si la cola no
        está disponible; el caso de uso la traduce.
        """
