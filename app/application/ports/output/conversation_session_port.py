from collections.abc import Mapping
from typing import Any, Protocol


class IConversationSessionPort(Protocol):
    """Estado de la conversación del bot con un cliente, uno por conversación del gateway.

    El estado es un objeto JSON (solo ``dict``, ``list``, ``str``, ``int``, ``float``,
    ``bool`` y ``None``) que el bot interpreta; el puerto no conoce su forma. Expira solo tras
    un periodo sin actividad: cada ``save`` lo renueva.
    """

    async def get(self, conversation_id: int) -> dict[str, Any] | None:
        """Estado guardado, o ``None`` si no existe, venció o no se puede leer."""

    async def save(self, conversation_id: int, state: Mapping[str, Any]) -> None:
        """Guarda el estado completo y renueva su vencimiento."""

    async def clear(self, conversation_id: int) -> None:
        """Olvida el estado; no falla si no existía."""
