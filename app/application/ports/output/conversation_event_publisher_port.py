from typing import Protocol

from app.application.dtos.conversation_event_dto import ConversationEvent


class IConversationEventPublisherPort(Protocol):
    """Difunde los eventos de la bandeja a los navegadores conectados (spec 09, sección 8)."""

    async def publish(self, event: ConversationEvent) -> None:
        """Publica el evento; sin búfer ni reenvío.

        La publicación es de mejor esfuerzo: quien llama captura cualquier excepción, la
        registra y sigue; nunca debe fallar un comando ni un trabajo por esto.
        """
