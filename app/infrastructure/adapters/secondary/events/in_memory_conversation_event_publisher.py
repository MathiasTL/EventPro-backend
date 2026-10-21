"""Publicador en memoria de los eventos de la bandeja, para pruebas y desarrollo sin Redis."""

from app.application.dtos.conversation_event_dto import ConversationEvent


class InMemoryConversationEventPublisher:
    """Guarda lo publicado en orden; con ``error``, ``publish`` falla (prueba de resiliencia)."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.events: list[ConversationEvent] = []
        self.error = error

    async def publish(self, event: ConversationEvent) -> None:
        if self.error is not None:
            raise self.error
        self.events.append(event)
