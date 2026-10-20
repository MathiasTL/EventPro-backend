"""WorkerSettings de arq: adaptador primario de tareas programadas (ADR-08).

Proceso aparte (servicio ``worker`` de Docker Compose). No contiene lógica de negocio: cada
tarea invoca un caso de uso. Despacha la cola ``outbox_messages`` y procesa los eventos que
entrega el webhook del gateway.
"""

import asyncio
import dataclasses
from datetime import UTC, datetime
from typing import Any

from arq import Retry, cron, func
from arq.connections import RedisSettings

from app.application.dtos.gateway_event_dto import GatewayEventOutcome
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.infrastructure.adapters.secondary.queue.arq_gateway_event_queue import (
    PROCESS_GATEWAY_EVENT_JOB,
)
from app.infrastructure.di.containers import (
    get_dispatch_due_messages_use_case,
    get_process_gateway_event_use_case,
    shutdown_infrastructure,
)

# Un ciclo cada 5 segundos. ``unique=True`` evita que dos workers ejecuten el mismo ciclo; el
# cerrojo del contexto evita que un ciclo lento se solape con el siguiente en el mismo worker.
DISPATCH_SECONDS = set(range(0, 60, 5))
# Menor que OUTBOX_LEASE_SECONDS (60 por defecto): si un ciclo se cancela, sus reservas vencen
# después y no antes de que termine, de modo que el lote no se reenvía a mitad de ciclo.
CYCLE_TIMEOUT_SECONDS = 55
# Eventos del gateway: cinco intentos con espera 5, 10, 20 y 40 s (unos 75 s en total) bastan para
# que un aviso que llegó antes de confirmarse SENT encuentre su mensaje; después se da por perdido.
GATEWAY_EVENT_MAX_TRIES = 5
GATEWAY_EVENT_TIMEOUT_SECONDS = 30
GATEWAY_EVENT_RETRY_BASE_SECONDS = 5


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["dispatch_lock"] = asyncio.Lock()
    ctx["dispatch_due_messages"] = get_dispatch_due_messages_use_case()
    ctx["process_gateway_event"] = get_process_gateway_event_use_case()
    if not settings.chatwoot_enabled:
        get_logger("worker").warning(
            "worker_using_fake_messaging",
            detail="Los mensajes se marcan SENT sin llegar a WhatsApp: falta CHATWOOT_BASE_URL.",
        )


async def shutdown(ctx: dict[str, Any]) -> None:
    await shutdown_infrastructure()


async def dispatch_outbox(ctx: dict[str, Any]) -> dict[str, int] | None:
    """Un ciclo de ``DispatchDueMessages``.

    Un error de base de datos aborta el ciclo y el siguiente lo reintenta.
    """

    lock: asyncio.Lock = ctx["dispatch_lock"]
    if lock.locked():
        get_logger("worker").warning("outbox_cycle_skipped_overlap")
        return None
    async with lock:
        summary = await ctx["dispatch_due_messages"].execute()
    if summary.claimed:
        get_logger("worker").info("outbox_cycle_done", **dataclasses.asdict(summary))
    return dataclasses.asdict(summary)


def _retry_delay_seconds(job_try: int) -> int:
    # Duplica la espera en cada intento: 5, 10, 20, 40 segundos.
    return GATEWAY_EVENT_RETRY_BASE_SECONDS << (job_try - 1)


async def process_gateway_event(
    ctx: dict[str, Any], raw_body: bytes, received_at_epoch: int
) -> str:
    """Procesa un evento firmado del gateway; reintenta de forma acotada.

    Se reintenta cuando el mensaje del aviso aún no existe (el despachador no confirmó SENT) o
    cuando el gateway no responde. En el último intento el trabajo termina sin error: arq no
    guarda resultados de este trabajo y reintentar más no ayudaría a un mensaje ajeno.
    """

    job_try = int(ctx.get("job_try", 1))
    last_attempt = job_try >= GATEWAY_EVENT_MAX_TRIES
    try:
        outcome: GatewayEventOutcome = await ctx["process_gateway_event"].execute(
            raw_body=raw_body,
            received_at=datetime.fromtimestamp(received_at_epoch, UTC),
            last_attempt=last_attempt,
        )
    except MessagingUnavailableError:
        if last_attempt:
            get_logger("worker").error("delivery_notice_lookup_failed", job_try=job_try)
            return "GATEWAY_UNAVAILABLE"
        raise Retry(defer=_retry_delay_seconds(job_try)) from None
    if outcome is GatewayEventOutcome.UNKNOWN_MESSAGE and not last_attempt:
        raise Retry(defer=_retry_delay_seconds(job_try))
    return outcome.value


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
        password=settings.redis_password or None,
    )


class WorkerSettings:
    functions: list[Any] = [
        func(
            process_gateway_event,
            name=PROCESS_GATEWAY_EVENT_JOB,
            max_tries=GATEWAY_EVENT_MAX_TRIES,
            keep_result=0,
            timeout=GATEWAY_EVENT_TIMEOUT_SECONDS,
        )
    ]
    cron_jobs = [
        cron(
            dispatch_outbox,
            name="dispatch_outbox",
            second=DISPATCH_SECONDS,
            run_at_startup=True,
            unique=True,
            timeout=CYCLE_TIMEOUT_SECONDS,
            max_tries=1,
        )
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
