import asyncio

from redis.asyncio import Redis

HEALTH_TIMEOUT_SECONDS = 2.0


class RedisCacheAdapter:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def ping(self) -> bool:
        try:
            async with asyncio.timeout(HEALTH_TIMEOUT_SECONDS):
                await self._client.ping()
            return True
        except Exception:
            return False
