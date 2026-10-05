"""Lock distribuido sobre Redis (``SET NX PX`` + liberación con token).

Garantiza exclusión mutua entre procesos (api y worker) para la verificación y reserva
de disponibilidad. La liberación es segura: solo borra la clave si el token almacenado
coincide con el de esta instancia (script Lua atómico).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import cast
from uuid import uuid4

from redis.asyncio import Redis

from app.application.ports.output.cache_lock_port import ICacheLockPort

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

_RETRY_INTERVAL_SECONDS = 0.05


class RedisLockAdapter(ICacheLockPort):
    """Lock distribuido respaldado en Redis."""

    def __init__(self, client: Redis) -> None:
        self._client = client
        self._tokens: dict[str, str] = {}

    async def acquire(self, key: str, *, ttl_seconds: int, wait_seconds: float = 0.0) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser mayor que cero")

        token = uuid4().hex
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds

        while True:
            acquired = await self._client.set(key, token, nx=True, px=ttl_seconds * 1000)
            if acquired:
                self._tokens[key] = token
                return True
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(_RETRY_INTERVAL_SECONDS)

    async def release(self, key: str) -> None:
        token = self._tokens.pop(key, None)
        if token is None:
            return
        await cast("Awaitable[object]", self._client.eval(_RELEASE_SCRIPT, 1, key, token))
