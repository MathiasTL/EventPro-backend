"""Publicador provisional que solo deja constancia en el log (el de Redis llega con B4)."""

from app.application.dtos.conversation_event_dto import ConversationEvent
from app.core.logging import get_logger


class LoggingConversationEventPublisher:
    """No difunde nada: registra el nombre del evento y la conversación, nunca el contenido."""

    async def publish(self, event: ConversationEvent) -> None:
        get_logger("conversation_events").debug(
            "conversation_event_published",
            event_name=event.event.value,
            conversation_id=event.data.get("chatwoot_conversation_id"),
        )
