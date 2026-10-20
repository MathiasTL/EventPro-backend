"""Adaptadores de ``IConversationSessionPort``: Redis (con un cliente simulado) y memoria."""

from typing import Any

import pytest

from app.application.ports.output.conversation_session_port import IConversationSessionPort
from app.infrastructure.adapters.secondary.cache.in_memory_conversation_session_adapter import (
    InMemoryConversationSessionAdapter,
)
from app.infrastructure.adapters.secondary.cache.redis_conversation_session_adapter import (
    DEFAULT_TTL_SECONDS,
    KEY_PREFIX,
    RedisConversationSessionAdapter,
)

STATE: dict[str, Any] = {"step": "PACKAGE", "options": [{"key": "a", "title": "Decoración"}]}


class _FakeRedis:
    """Cliente mínimo con los tres comandos que usa el adaptador; registra el vencimiento."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _redis_adapter(client: _FakeRedis | None = None) -> IConversationSessionPort:
    return RedisConversationSessionAdapter(client or _FakeRedis())  # type: ignore[arg-type]


@pytest.fixture(params=["redis", "memory"])
def adapter(request: pytest.FixtureRequest) -> IConversationSessionPort:
    if request.param == "redis":
        return _redis_adapter()
    return InMemoryConversationSessionAdapter()


async def test_a_missing_session_is_none(adapter: IConversationSessionPort) -> None:
    assert await adapter.get(1) is None


async def test_a_saved_session_is_returned_equal_but_not_shared(
    adapter: IConversationSessionPort,
) -> None:
    await adapter.save(1, STATE)

    loaded = await adapter.get(1)

    assert loaded == STATE
    assert loaded is not STATE


async def test_sessions_are_isolated_by_conversation(adapter: IConversationSessionPort) -> None:
    await adapter.save(1, {"step": "A"})
    await adapter.save(2, {"step": "B"})

    assert await adapter.get(1) == {"step": "A"}
    assert await adapter.get(2) == {"step": "B"}


async def test_saving_again_replaces_the_state(adapter: IConversationSessionPort) -> None:
    await adapter.save(1, {"step": "A"})
    await adapter.save(1, {"step": "B"})

    assert await adapter.get(1) == {"step": "B"}


async def test_clear_forgets_the_state_and_tolerates_a_missing_one(
    adapter: IConversationSessionPort,
) -> None:
    await adapter.save(1, STATE)

    await adapter.clear(1)
    await adapter.clear(1)

    assert await adapter.get(1) is None


async def test_the_redis_adapter_stores_json_with_a_24_hour_expiration() -> None:
    client = _FakeRedis()

    await _redis_adapter(client).save(57, {"nombre": "Ñandú"})

    key = f"{KEY_PREFIX}57"
    assert client.values[key] == '{"nombre": "Ñandú"}'
    assert client.expirations[key] == DEFAULT_TTL_SECONDS == 86_400


async def test_the_redis_adapter_honors_a_custom_expiration() -> None:
    client = _FakeRedis()

    await RedisConversationSessionAdapter(client, ttl_seconds=60).save(  # type: ignore[arg-type]
        1, STATE
    )

    assert client.expirations[f"{KEY_PREFIX}1"] == 60


@pytest.mark.parametrize("raw", ["no es json", "[1, 2]", '"texto"'])
async def test_an_unreadable_state_is_dropped_instead_of_blocking_the_conversation(
    raw: str,
) -> None:
    client = _FakeRedis()
    client.values[f"{KEY_PREFIX}1"] = raw

    assert await _redis_adapter(client).get(1) is None
    assert f"{KEY_PREFIX}1" not in client.values


def test_the_redis_adapter_rejects_a_non_positive_expiration() -> None:
    with pytest.raises(ValueError):
        RedisConversationSessionAdapter(_FakeRedis(), ttl_seconds=0)  # type: ignore[arg-type]
