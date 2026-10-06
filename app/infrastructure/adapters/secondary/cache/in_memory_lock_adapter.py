"""Lock en memoria (sin TTL real).

Útil para pruebas unitarias y para desarrollo sin Redis. **No** es distribuido: solo
serializa dentro de un mismo proceso.
"""

from __future__ import annotations

from app.application.ports.output.cache_lock_port import ICacheLockPort


class InMemoryLockAdapter(ICacheLockPort):
    """Lock por proceso basado en un conjunto de claves tomadas."""

    def __init__(self) -> None:
        self._held: set[str] = set()

    async def acquire(self, key: str, *, ttl_seconds: int, wait_seconds: float = 0.0) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser mayor que cero")
        if key in self._held:
            return False
        self._held.add(key)
        return True

    async def release(self, key: str) -> None:
        self._held.discard(key)

    def is_locked(self, key: str) -> bool:
        """Indica si la clave está tomada (solo para pruebas/introspección)."""

        return key in self._held
