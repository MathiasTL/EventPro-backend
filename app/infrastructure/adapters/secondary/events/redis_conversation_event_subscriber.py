"""Suscriptor de los eventos de la bandeja sobre Redis *pub/sub* (spec 09, D4)."""

import asyncio
import json
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.application.dtos.conversation_event_dto import ConversationEvent
from app.application.ports.output.conversation_event_subscriber_port import (
    IConversationEventSubscriptionPort,
)
from app.core.logging import get_logger
from app.infrastructure.adapters.secondary.events.redis_conversation_event_publisher import (
    CONVERSATION_EVENTS_CHANNEL,
)


class RedisConversationEventSubscription:
    """Una conexión *pub/sub* propia de una conexión SSE."""

    def __init__(self, pubsub: PubSub) -> None:
        self._pubsub = pubsub

    async def next_event(self, timeout: float) -> ConversationEvent | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout, 0.0)
        while True:
            remaining = max(deadline - loop.time(), 0.0)
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True, timeout=remaining
            )
            if message is not None:
                event = _parse(message.get("data"))
                if event is not None:
                    return event
            if loop.time() >= deadline:
                return None

    async def close(self) -> None:
        try:
            await self._pubsub.aclose()  # type: ignore[no-untyped-call]
        except Exception as exc:
            get_logger("conversation_events").warning(
                "conversation_event_unsubscribe_failed", error_type=type(exc).__name__
            )


class RedisConversationEventSubscriber:
    def __init__(self, redis: Redis, *, channel: str = CONVERSATION_EVENTS_CHANNEL) -> None:
        self._redis = redis
        self._channel = channel

    async def subscribe(self) -> IConversationEventSubscriptionPort:
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(self._channel)
        except BaseException:
            await pubsub.aclose()  # type: ignore[no-untyped-call]
            raise
        return RedisConversationEventSubscription(pubsub)


def _parse(raw: Any) -> ConversationEvent | None:
    """Convierte el mensaje del canal; lo ilegible o desconocido se descarta con un aviso."""

    try:
        return ConversationEvent.from_envelope(json.loads(raw))
    except (TypeError, ValueError, KeyError):
        get_logger("conversation_events").warning("conversation_event_discarded")
        return None
