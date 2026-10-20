"""Estado de la conversación del bot sobre Redis: un JSON por conversación con vencimiento."""

import json
from collections.abc import Mapping
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

KEY_PREFIX = "eventpro:bot:session:"
# La ventana de servicio de WhatsApp dura 24 h: pasado ese plazo sin actividad no se retoma.
DEFAULT_TTL_SECONDS = 24 * 60 * 60


class RedisConversationSessionAdapter:
    """Implementa ``IConversationSessionPort`` con ``SET EX``, ``GET`` y ``DEL``."""

    def __init__(self, client: Redis, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser mayor que cero")
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def get(self, conversation_id: int) -> dict[str, Any] | None:
        raw = await self._client.get(_key(conversation_id))
        if raw is None:
            return None
        try:
            state = json.loads(raw)
        except ValueError:
            state = None
        if not isinstance(state, dict):
            # Un estado ilegible no debe dejar a la conversación atascada: se descarta.
            get_logger("bot_session").warning(
                "bot_session_unreadable", conversation_id=conversation_id
            )
            await self._client.delete(_key(conversation_id))
            return None
        return state

    async def save(self, conversation_id: int, state: Mapping[str, Any]) -> None:
        await self._client.set(
            _key(conversation_id),
            json.dumps(state, ensure_ascii=False),
            ex=self._ttl_seconds,
        )

    async def clear(self, conversation_id: int) -> None:
        await self._client.delete(_key(conversation_id))


def _key(conversation_id: int) -> str:
    return f"{KEY_PREFIX}{conversation_id}"
