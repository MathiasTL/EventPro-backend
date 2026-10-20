"""Cola de eventos del gateway sobre arq.

Define el nombre del trabajo y la espera inicial (el worker los importa desde aquí) y el
adaptador con el que la API encola cada evento verificado.
"""

from datetime import datetime

from arq.connections import ArqRedis

# Nombre con el que el worker registra el trabajo y con el que la API lo encola.
PROCESS_GATEWAY_EVENT_JOB = "process_gateway_event"
# Espera antes de la primera ejecución: deja que el despachador confirme SENT con el id del mensaje
# antes de que llegue su aviso de entrega.
GATEWAY_EVENT_DEFER_SECONDS = 2


class ArqGatewayEventQueue:
    """Implementa ``IGatewayEventQueuePort`` encolando ``process_gateway_event`` en arq."""

    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def enqueue(self, *, event_id: str, raw_body: bytes, received_at: datetime) -> None:
        # Los argumentos coinciden con ``process_gateway_event(ctx, raw_body, received_at_epoch)``.
        # ``_job_id`` evita duplicados mientras el trabajo está en cola; arq devuelve ``None`` si
        # ya existe, y eso no es un error: la clave de Redis es la guarda duradera.
        await self._pool.enqueue_job(
            PROCESS_GATEWAY_EVENT_JOB,
            raw_body,
            int(received_at.timestamp()),
            _job_id=f"chatwoot:{event_id}",
            _defer_by=GATEWAY_EVENT_DEFER_SECONDS,
        )
