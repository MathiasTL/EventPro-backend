"""Deduplicación de eventos del gateway sobre Redis (``SET NX EX`` y ``DEL``)."""

from redis.asyncio import Redis

KEY_PREFIX = "eventpro:chatwoot:webhook:"


class RedisEventDedupAdapter:
    """Implementa ``IEventDedupPort``: la clave existe mientras el evento cuenta como recibido."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def claim(self, event_id: str, *, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser mayor que cero")
        # ``SET NX`` es atómico: de varias recepciones simultáneas solo una obtiene la clave.
        return bool(await self._client.set(f"{KEY_PREFIX}{event_id}", "1", nx=True, ex=ttl_seconds))

    async def release(self, event_id: str) -> None:
        await self._client.delete(f"{KEY_PREFIX}{event_id}")
