"""Pruebas unitarias de los adaptadores de lock (en memoria) y del puerto."""

from __future__ import annotations

import asyncio

import pytest

from app.application.ports.output.cache_lock_port import ICacheLockPort
from app.infrastructure.adapters.secondary.cache import InMemoryLockAdapter


def test_lock_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        ICacheLockPort()  # type: ignore[abstract]


def test_in_memory_lock_lifecycle() -> None:
    lock = InMemoryLockAdapter()

    async def _run() -> None:
        assert not lock.is_locked("catalog")
        assert await lock.acquire("catalog", ttl_seconds=10)
        assert lock.is_locked("catalog")
        assert not await lock.acquire("catalog", ttl_seconds=10)
        await lock.release("catalog")
        assert not lock.is_locked("catalog")
        assert await lock.acquire("catalog", ttl_seconds=10)
        await lock.release("catalog")

    asyncio.run(_run())


def test_in_memory_lock_invalid_ttl() -> None:
    lock = InMemoryLockAdapter()

    async def _run() -> None:
        with pytest.raises(ValueError):
            await lock.acquire("k", ttl_seconds=0)

    asyncio.run(_run())


def test_in_memory_release_unlocked_is_noop() -> None:
    lock = InMemoryLockAdapter()
    asyncio.run(lock.release("nope"))
    assert not lock.is_locked("nope")
