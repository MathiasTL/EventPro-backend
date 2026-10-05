"""Prueba de integración del lock distribuido sobre Redis real (Testcontainers).

Marcada como ``integration``; correr con ``pytest -m integration``.
"""

from __future__ import annotations

import asyncio

import pytest
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer

from app.infrastructure.adapters.secondary.cache import RedisLockAdapter

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def redis_url() -> str:
    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


def test_redis_lock_lifecycle(redis_url: str) -> None:
    async def _run() -> None:
        client = Redis.from_url(redis_url)
        lock = RedisLockAdapter(client)
        try:
            assert await lock.acquire("availability", ttl_seconds=10)
            # Ya tomado: no se vuelve a adquirir.
            assert not await lock.acquire("availability", ttl_seconds=10)
            await lock.release("availability")
            # Liberado: se puede volver a tomar.
            assert await lock.acquire("availability", ttl_seconds=10)
            await lock.release("availability")
            # Liberar sin tenerlo no rompe.
            await lock.release("availability")
        finally:
            await client.aclose()

    asyncio.run(_run())
