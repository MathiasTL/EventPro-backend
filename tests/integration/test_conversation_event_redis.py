"""Publicador y suscriptor de eventos de la bandeja sobre Redis real (Testcontainers)."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.application.dtos.conversation_event_dto import ConversationEvent, ConversationEventType
from app.infrastructure.adapters.secondary.events.redis_conversation_event_publisher import (
    RedisConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.events.redis_conversation_event_subscriber import (
    RedisConversationEventSubscriber,
)
from app.infrastructure.di.containers import get_redis_client

pytestmark = pytest.mark.integration

EVENT = ConversationEvent(
    ConversationEventType.MESSAGE_CREATED,
    {"chatwoot_conversation_id": 57, "message": {"content": "hola ñ"}},
)


@pytest.fixture
async def redis(infra: None) -> AsyncIterator[Redis]:
    yield get_redis_client()


async def test_a_published_event_reaches_every_subscriber(redis: Redis) -> None:
    subscriber = RedisConversationEventSubscriber(redis)
    first = await subscriber.subscribe()
    second = await subscriber.subscribe()
    try:
        await RedisConversationEventPublisher(redis).publish(EVENT)

        assert await first.next_event(2) == EVENT
        assert await second.next_event(2) == EVENT
    finally:
        await first.close()
        await second.close()


async def test_there_is_no_replay_for_a_late_subscriber(redis: Redis) -> None:
    await RedisConversationEventPublisher(redis).publish(EVENT)

    late = await RedisConversationEventSubscriber(redis).subscribe()
    try:
        assert await late.next_event(0.3) is None
    finally:
        await late.close()


async def test_next_event_waits_for_the_timeout_and_ignores_malformed_messages(
    redis: Redis,
) -> None:
    subscription = await RedisConversationEventSubscriber(redis).subscribe()
    try:
        waiting = asyncio.create_task(subscription.next_event(2))
        await asyncio.sleep(0.1)
        await redis.publish("eventpro:conversations:events", "not json")
        await redis.publish("eventpro:conversations:events", '{"v":1,"event":"x.y","data":{}}')
        await RedisConversationEventPublisher(redis).publish(EVENT)

        assert await waiting == EVENT
        assert await subscription.next_event(0.2) is None
    finally:
        await subscription.close()
        await subscription.close()
