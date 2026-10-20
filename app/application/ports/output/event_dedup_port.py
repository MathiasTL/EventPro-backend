from typing import Protocol


class IEventDedupPort(Protocol):
    """Memoria de los eventos ya recibidos, para no encolar dos veces el mismo."""

    async def claim(self, event_id: str, *, ttl_seconds: int) -> bool:
        """Reclama el identificador de forma atómica.

        Devuelve ``True`` la primera vez que se ve dentro del TTL y ``False`` si ya estaba.
        """

    async def release(self, event_id: str) -> None:
        """Olvida el identificador para que el evento pueda recibirse de nuevo."""
