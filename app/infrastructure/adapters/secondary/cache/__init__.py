"""Adaptadores de caché y locks distribuidos."""

from .in_memory_lock_adapter import InMemoryLockAdapter
from .redis_lock_adapter import RedisLockAdapter

__all__ = ["InMemoryLockAdapter", "RedisLockAdapter"]
