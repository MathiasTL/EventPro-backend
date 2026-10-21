"""Marcar una conversación como leída (spec 09, 6.8, D13)."""

from dataclasses import replace

from app.application.ports.output.conversation_event_publisher_port import (
    IConversationEventPublisherPort,
)
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.use_cases.messaging.conversation_events import conversation_view_event
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.core.logging import get_logger


class MarkConversationRead:
    """Reinicia el contador compartido en Chatwoot y avisa a la bandeja (mejor esfuerzo)."""

    def __init__(
        self,
        messaging: IMessagingPort,
        views: ConversationViewBuilder,
        publisher: IConversationEventPublisherPort,
    ) -> None:
        self._messaging = messaging
        self._views = views
        self._publisher = publisher

    async def execute(self, conversation_id: int) -> None:
        """Lanza ``ResourceNotFoundError`` o ``MessagingUnavailableError`` si Chatwoot falla.

        Publicar ``conversation.updated`` con ``unread_count = 0`` nunca falla el comando.
        """

        await self._messaging.mark_conversation_read(conversation_id)
        try:
            summary = await self._messaging.get_conversation(conversation_id)
            (view,) = await self._views.build([replace(summary, unread_count=0)])
            await self._publisher.publish(conversation_view_event(view))
        except Exception as exc:
            get_logger("conversation_read").warning(
                "conversation_read_event_failed",
                conversation_id=conversation_id,
                error_type=type(exc).__name__,
            )
