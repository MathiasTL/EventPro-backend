"""WorkerSettings de arq: adaptador primario de tareas programadas (ADR-08).

Proceso aparte (servicio ``worker`` de Docker Compose). No contiene lógica de negocio: cada
tarea invoca un caso de uso. Hoy solo despacha la cola ``outbox_messages``.
"""

import asyncio
import dataclasses
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.adapters.secondary.persistence.database import get_engine
from app.infrastructure.di.containers import get_dispatch_due_messages_use_case

# Un ciclo cada 5 segundos. ``unique=True`` evita que dos workers ejecuten el mismo ciclo; el
# cerrojo del contexto evita que un ciclo lento se solape con el siguiente en el mismo worker.
DISPATCH_SECONDS = set(range(0, 60, 5))
# Menor que OUTBOX_LEASE_SECONDS (60 por defecto): si un ciclo se cancela, sus reservas vencen
# después y no antes de que termine, de modo que el lote no se reenvía a mitad de ciclo.
CYCLE_TIMEOUT_SECONDS = 55


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["dispatch_lock"] = asyncio.Lock()
    ctx["dispatch_due_messages"] = get_dispatch_due_messages_use_case()
    get_logger("worker").warning(
        "worker_using_fake_messaging",
        detail="Los mensajes se marcan SENT sin llegar a WhatsApp hasta que exista "
        "ChatwootMessagingAdapter.",
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    await get_engine().dispose()


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


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
        password=settings.redis_password or None,
    )


class WorkerSettings:
    functions: list[Any] = []
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
