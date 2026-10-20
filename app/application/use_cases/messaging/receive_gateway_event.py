"""Caso de uso ReceiveGatewayEvent: reclamar el id, encolar y liberar si el encolado falla.

El orden es la regla: un evento reclamado que no pudo encolarse debe liberarse para que un
reenvío posterior sí se procese. El cuerpo viaja sin interpretarse.
"""

from datetime import datetime

from app.application.ports.output.event_dedup_port import IEventDedupPort
from app.application.ports.output.gateway_event_queue_port import IGatewayEventQueuePort
from app.application.use_cases.messaging.errors import GatewayEventNotQueuedError
from app.core.logging import get_logger

# Chatwoot no reintenta sus webhooks de cuenta; siete días cubren reenvíos manuales.
EVENT_DEDUP_TTL_SECONDS = 604_800


class ReceiveGatewayEvent:
    """Deduplica por identificador de entrega y encola el evento para el worker."""

    def __init__(self, dedup: IEventDedupPort, queue: IGatewayEventQueuePort) -> None:
        self._dedup = dedup
        self._queue = queue

    async def execute(self, *, event_id: str, raw_body: bytes, received_at: datetime) -> bool:
        """``True`` si se encoló, ``False`` si era un duplicado.

        Lanza ``GatewayEventNotQueuedError`` si el reclamo o el encolado fallan.
        """

        try:
            claimed = await self._dedup.claim(event_id, ttl_seconds=EVENT_DEDUP_TTL_SECONDS)
        except Exception as exc:
            raise GatewayEventNotQueuedError(event_id, type(exc).__name__) from exc
        if not claimed:
            return False
        try:
            await self._queue.enqueue(event_id=event_id, raw_body=raw_body, received_at=received_at)
        except Exception as exc:
            await self._release(event_id)
            raise GatewayEventNotQueuedError(event_id, type(exc).__name__) from exc
        return True

    async def _release(self, event_id: str) -> None:
        try:
            await self._dedup.release(event_id)
        except Exception as exc:
            # Los loggers se crean en cada llamada: structlog cachea el primero tras configurarse.
            # Sin ``event_id``: puede ser el resumen de la firma y los logs nunca llevan firmas.
            get_logger("gateway_events").warning(
                "gateway_event_release_failed", error_type=type(exc).__name__
            )
