"""Router HTTP de la bandeja de conversaciones (spec 09).

``/conversations/stream`` se declara antes que cualquier ruta ``/conversations/{id}`` que
agreguen los bloques siguientes, para que el literal no se interprete como identificador.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.application.ports.output.conversation_event_subscriber_port import (
    IConversationEventSubscriberPort,
)
from app.infrastructure.adapters.primary.web.deps import (
    StreamAuthContext,
    get_stream_auth_context,
)
from app.infrastructure.adapters.primary.web.sse import event_stream
from app.infrastructure.di import containers

router = APIRouter(prefix="/conversations", tags=["Conversaciones"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/stream", response_class=StreamingResponse)
async def stream_conversation_events(
    request: Request,
    auth: Annotated[StreamAuthContext, Depends(get_stream_auth_context)],
    subscriber: Annotated[
        IConversationEventSubscriberPort, Depends(containers.get_conversation_event_subscriber)
    ],
) -> StreamingResponse:
    """Eventos de la bandeja en tiempo real (SSE); la autenticación ocurre antes del stream."""
    return StreamingResponse(
        event_stream(
            subscriber,
            expires_at=auth.expires_at,
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
