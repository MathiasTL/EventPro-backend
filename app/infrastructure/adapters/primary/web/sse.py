"""Tramas y ciclo de vida del stream SSE de la bandeja (spec 09, sección 8)."""

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

import anyio

from app.application.dtos.conversation_event_dto import ConversationEvent
from app.application.ports.output.conversation_event_subscriber_port import (
    IConversationEventSubscriberPort,
)
from app.core.logging import get_logger

KEEPALIVE_SECONDS = 25.0
RETRY_MILLISECONDS = 3000
KEEPALIVE_FRAME = ": keepalive\n\n"
RETRY_FRAME = f"retry: {RETRY_MILLISECONDS}\n\n"


def format_event(event: ConversationEvent) -> str:
    """``event: <nombre>`` y ``data: <json>``; ``data`` es la carga, sin el sobre."""

    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event.value}\ndata: {payload}\n\n"


async def event_stream(
    subscriber: IConversationEventSubscriberPort,
    *,
    expires_at: float,
    is_disconnected: Callable[[], Awaitable[bool]],
    now: Callable[[], float] = time.time,
    keepalive_seconds: float = KEEPALIVE_SECONDS,
) -> AsyncIterator[str]:
    """Emite los eventos del canal hasta que vence el token o se desconecta el cliente.

    El latido se envía si pasaron ``keepalive_seconds`` sin tráfico. Si Redis falla, el stream
    termina y el cliente reconecta. La suscripción se libera siempre al salir.
    """

    subscription = None
    try:
        subscription = await subscriber.subscribe()
        yield RETRY_FRAME
        last_sent = now()
        while True:
            current = now()
            if current >= expires_at or await is_disconnected():
                return
            wait = min(last_sent + keepalive_seconds - current, expires_at - current)
            event = await subscription.next_event(max(wait, 0.0))
            if event is not None:
                yield format_event(event)
                last_sent = now()
            elif now() - last_sent >= keepalive_seconds:
                yield KEEPALIVE_FRAME
                last_sent = now()
    except Exception as exc:
        get_logger("conversation_events").warning(
            "conversation_stream_closed", error_type=type(exc).__name__
        )
    finally:
        if subscription is not None:
            # Protegido de la cancelación: al desconectarse el cliente, Starlette cancela la
            # tarea y el cierre debe terminar para no dejar abierta la conexión de Redis.
            with anyio.CancelScope(shield=True):
                await subscription.close()
