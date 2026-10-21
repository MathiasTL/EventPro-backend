"""Stream SSE de la bandeja: tramas, latido, cierre por vencimiento y limpieza."""

import json

from app.application.dtos.conversation_event_dto import ConversationEvent, ConversationEventType
from app.infrastructure.adapters.primary.web.sse import (
    KEEPALIVE_FRAME,
    RETRY_FRAME,
    event_stream,
    format_event,
)

EVENT = ConversationEvent(
    ConversationEventType.HANDOFF_REQUESTED,
    {"chatwoot_conversation_id": 57, "handoff_summary": "Cotización q9c8, 15/10 ñ"},
)


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


class FakeSubscription:
    """Avanza el reloj lo que dura la espera, como un canal sin tráfico."""

    def __init__(self, clock: Clock, script: list[ConversationEvent | Exception | None]) -> None:
        self.clock = clock
        self.script = script
        self.timeouts: list[float] = []
        self.closed = 0

    async def next_event(self, timeout: float) -> ConversationEvent | None:
        self.timeouts.append(timeout)
        step = self.script.pop(0) if self.script else None
        if isinstance(step, Exception):
            raise step
        if step is None:
            self.clock.value += timeout
        return step

    async def close(self) -> None:
        self.closed += 1


class FakeSubscriber:
    def __init__(self, subscription: FakeSubscription | None = None) -> None:
        self.subscription = subscription
        self.error: Exception | None = None

    async def subscribe(self) -> FakeSubscription:
        if self.error is not None:
            raise self.error
        assert self.subscription is not None
        return self.subscription


async def _never_disconnected() -> bool:
    return False


async def _collect(subscriber: FakeSubscriber, clock: Clock, expires_at: float) -> list[str]:
    return [
        frame
        async for frame in event_stream(
            subscriber,
            expires_at=expires_at,
            is_disconnected=_never_disconnected,
            now=clock,
        )
    ]


def test_an_event_is_formatted_as_name_and_json_payload_without_the_envelope() -> None:
    frame = format_event(EVENT)

    name_line, data_line, blank = frame.split("\n", 2)
    assert name_line == "event: handoff.requested"
    assert frame.endswith("\n\n")
    assert json.loads(data_line.removeprefix("data: ")) == dict(EVENT.data)
    assert "ñ" in data_line
    assert blank == "\n"


async def test_it_opens_with_retry_then_forwards_events_in_order() -> None:
    clock = Clock()
    second = ConversationEvent(ConversationEventType.CONVERSATION_UPDATED, {"id": 1})
    subscription = FakeSubscription(clock, [EVENT, second])

    frames = await _collect(FakeSubscriber(subscription), clock, expires_at=clock.value + 100)

    assert frames[0] == RETRY_FRAME
    assert frames[1:3] == [format_event(EVENT), format_event(second)]


async def test_it_sends_a_keepalive_every_25_seconds_without_traffic() -> None:
    clock = Clock()
    subscription = FakeSubscription(clock, [])

    frames = await _collect(FakeSubscriber(subscription), clock, expires_at=clock.value + 60)

    assert frames.count(KEEPALIVE_FRAME) == 2
    assert subscription.timeouts[0] == 25.0


async def test_traffic_postpones_the_keepalive() -> None:
    clock = Clock()
    subscription = FakeSubscription(clock, [None, EVENT])

    frames = await _collect(FakeSubscriber(subscription), clock, expires_at=clock.value + 40)

    # 25 s de silencio -> latido; el evento reinicia el contador; quedan 15 s hasta el vencimiento.
    assert frames == [RETRY_FRAME, KEEPALIVE_FRAME, format_event(EVENT)]


async def test_it_closes_when_the_token_expires_and_releases_the_subscription() -> None:
    clock = Clock()
    subscription = FakeSubscription(clock, [])

    frames = await _collect(FakeSubscriber(subscription), clock, expires_at=clock.value + 10)

    assert frames == [RETRY_FRAME]
    assert subscription.timeouts == [10.0]
    assert subscription.closed == 1


async def test_it_closes_on_a_token_that_is_already_expired() -> None:
    clock = Clock()
    subscription = FakeSubscription(clock, [EVENT])

    frames = await _collect(FakeSubscriber(subscription), clock, expires_at=clock.value - 1)

    assert frames == [RETRY_FRAME]
    assert subscription.closed == 1


async def test_it_stops_when_the_client_disconnects() -> None:
    clock = Clock()
    subscription = FakeSubscription(clock, [EVENT, EVENT])
    checks = iter([False, True])

    async def disconnected() -> bool:
        return next(checks)

    frames = [
        frame
        async for frame in event_stream(
            FakeSubscriber(subscription),
            expires_at=clock.value + 100,
            is_disconnected=disconnected,
            now=clock,
        )
    ]

    assert frames == [RETRY_FRAME, format_event(EVENT)]
    assert subscription.closed == 1


async def test_it_closes_the_stream_and_the_subscription_when_redis_fails() -> None:
    clock = Clock()
    subscription = FakeSubscription(clock, [EVENT, ConnectionError("redis down")])

    frames = await _collect(FakeSubscriber(subscription), clock, expires_at=clock.value + 100)

    assert frames == [RETRY_FRAME, format_event(EVENT)]
    assert subscription.closed == 1


async def test_it_ends_quietly_when_the_subscription_cannot_be_opened() -> None:
    subscriber = FakeSubscriber()
    subscriber.error = ConnectionError("redis down")

    assert await _collect(subscriber, Clock(), expires_at=2000.0) == []
