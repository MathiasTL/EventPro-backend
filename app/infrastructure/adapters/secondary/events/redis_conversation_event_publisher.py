"""Publicador de los eventos de la bandeja sobre Redis *pub/sub* (spec 09, D4)."""

import json

from redis.asyncio import Redis

from app.application.dtos.conversation_event_dto import ConversationEvent
from app.core.logging import get_logger

CONVERSATION_EVENTS_CHANNEL = "eventpro:conversations:events"


class RedisConversationEventPublisher:
    """Difunde el sobre JSON por el canal único; una falla se registra y nunca se propaga."""

    def __init__(self, redis: Redis, *, channel: str = CONVERSATION_EVENTS_CHANNEL) -> None:
        self._redis = redis
        self._channel = channel

    async def publish(self, event: ConversationEvent) -> None:
        try:
            payload = json.dumps(event.to_envelope(), ensure_ascii=False)
            await self._redis.publish(self._channel, payload)
        except Exception as exc:
            # Mejor esfuerzo: el estado ya cambió y la interfaz se recupera con el refetch.
            get_logger("conversation_events").warning(
                "conversation_event_publish_failed",
                event_name=event.event.value,
                error_type=type(exc).__name__,
            )
