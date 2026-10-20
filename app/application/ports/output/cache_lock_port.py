"""Puerto de salida de locks distribuidos (ADR-06).

Se usa para serializar la verificación y reserva de disponibilidad (evitar la doble
reserva o sobreventa bajo concurrencia). La implementación por defecto vive en
infraestructura (Redis).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ICacheLockPort(ABC):
    """Adquisición y liberación de un lock distribuido por clave."""

    @abstractmethod
    async def acquire(self, key: str, *, ttl_seconds: int, wait_seconds: float = 0.0) -> bool:
        """Intenta tomar el lock ``key``.

        Reintenta hasta ``wait_seconds``; devuelve ``False`` si no lo consigue. El lock
        expira solo tras ``ttl_seconds`` para no quedar bloqueado ante un fallo.
        """

    @abstractmethod
    async def release(self, key: str) -> None:
        """Libera el lock ``key`` si esta instancia es su dueña."""
