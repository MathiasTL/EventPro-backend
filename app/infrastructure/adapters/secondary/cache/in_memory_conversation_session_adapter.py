"""Estado de la conversación del bot en memoria: para pruebas y desarrollo sin Redis."""

import json
from collections.abc import Mapping
from typing import Any


class InMemoryConversationSessionAdapter:
    """Implementa ``IConversationSessionPort`` sobre un diccionario.

    Guarda el JSON serializado, como Redis, para que una prueba detecte estado que no sea
    serializable y para que lo leído no comparta objetos con lo guardado. No vence.
    """

    def __init__(self) -> None:
        self._states: dict[int, str] = {}

    async def get(self, conversation_id: int) -> dict[str, Any] | None:
        raw = self._states.get(conversation_id)
        if raw is None:
            return None
        state: dict[str, Any] = json.loads(raw)
        return state

    async def save(self, conversation_id: int, state: Mapping[str, Any]) -> None:
        self._states[conversation_id] = json.dumps(state, ensure_ascii=False)

    async def clear(self, conversation_id: int) -> None:
        self._states.pop(conversation_id, None)
