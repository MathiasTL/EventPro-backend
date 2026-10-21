from typing import Protocol

from app.application.dtos.conversation_event_dto import ConversationEvent


class IConversationEventSubscriptionPort(Protocol):
    """Suscripción abierta de una conexión SSE al canal de eventos de la bandeja."""

    async def next_event(self, timeout: float) -> ConversationEvent | None:
        """Espera el siguiente evento hasta ``timeout`` segundos; ``None`` si no llegó ninguno.

        Si el canal falla, lanza la excepción: quien consume cierra el stream.
        """

    async def close(self) -> None:
        """Libera la suscripción; es seguro llamarla más de una vez."""


class IConversationEventSubscriberPort(Protocol):
    """Abre suscripciones al canal de eventos de la bandeja (spec 09, sección 8)."""

    async def subscribe(self) -> IConversationEventSubscriptionPort:
        """Abre una suscripción nueva; sin búfer ni reenvío de lo anterior."""
