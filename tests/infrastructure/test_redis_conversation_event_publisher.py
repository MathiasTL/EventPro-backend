"""Publicador Redis: sobre JSON en el canal único y falla sin propagar."""

import json
from typing import Any

from structlog.testing import capture_logs

from app.application.dtos.conversation_event_dto import ConversationEvent, ConversationEventType
from app.core.logging import configure_logging
from app.infrastructure.adapters.secondary.events.redis_conversation_event_publisher import (
    CONVERSATION_EVENTS_CHANNEL,
    RedisConversationEventPublisher,
)

EVENT = ConversationEvent(
    ConversationEventType.MESSAGE_CREATED,
    {"chatwoot_conversation_id": 57, "message": {"content": "texto privado ñ"}},
)


class FakeRedis:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        if self.error is not None:
            raise self.error
        self.published.append((channel, payload))
        return 1


def _publisher(redis: FakeRedis) -> RedisConversationEventPublisher:
    fake: Any = redis
    return RedisConversationEventPublisher(fake)


async def test_it_publishes_the_versioned_envelope_on_the_single_channel() -> None:
    redis = FakeRedis()

    await _publisher(redis).publish(EVENT)

    [(channel, payload)] = redis.published
    assert channel == "eventpro:conversations:events" == CONVERSATION_EVENTS_CHANNEL
    assert json.loads(payload) == EVENT.to_envelope()


async def test_a_redis_failure_is_logged_and_swallowed_without_leaking_content() -> None:
    configure_logging("DEBUG")
    redis = FakeRedis(error=ConnectionError("redis down"))

    with capture_logs() as logs:
        await _publisher(redis).publish(EVENT)

    [entry] = [log for log in logs if log["event"] == "conversation_event_publish_failed"]
    assert entry["event_name"] == "message.created"
    assert entry["error_type"] == "ConnectionError"
    assert "texto privado" not in str(logs)


async def test_a_serialization_failure_is_also_swallowed() -> None:
    redis = FakeRedis()
    bad = ConversationEvent(ConversationEventType.MESSAGE_CREATED, {"x": object()})

    await _publisher(redis).publish(bad)

    assert redis.published == []
