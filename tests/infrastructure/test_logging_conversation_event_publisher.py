"""Publicador provisional: registra el evento sin contenido de mensajes."""

from structlog.testing import capture_logs

from app.application.dtos.conversation_event_dto import ConversationEvent, ConversationEventType
from app.core.logging import configure_logging
from app.infrastructure.adapters.secondary.events.logging_conversation_event_publisher import (
    LoggingConversationEventPublisher,
)


async def test_it_logs_the_event_name_and_conversation_but_never_the_content() -> None:
    configure_logging("DEBUG")
    event = ConversationEvent(
        ConversationEventType.MESSAGE_CREATED,
        {"chatwoot_conversation_id": 57, "message": {"content": "texto privado"}},
    )

    with capture_logs() as logs:
        await LoggingConversationEventPublisher().publish(event)

    assert logs == [
        {
            "event": "conversation_event_published",
            "event_name": "message.created",
            "conversation_id": 57,
            "log_level": "debug",
        }
    ]
