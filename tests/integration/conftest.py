"""Fixtures de integración: PostgreSQL y Redis reales con testcontainers.

``infra`` (sesión) levanta PostgreSQL + Redis, exporta sus variables de entorno y aplica
las migraciones con Alembic. ``database_url`` (módulo) entrega un PostgreSQL efímero a
las pruebas de catálogo (E3), con un contenedor limpio por módulo de prueba.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.core.config import get_settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def infra() -> Iterator[None]:
    with (
        PostgresContainer("postgres:16-alpine") as postgres,
        RedisContainer("redis:7-alpine") as redis,
    ):
        connection_url = postgres.get_connection_url()
        os.environ["DATABASE_URL"] = connection_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        os.environ["REDIS_HOST"] = redis.get_container_host_ip()
        os.environ["REDIS_PORT"] = str(redis.get_exposed_port(6379))

        get_settings.cache_clear()
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            check=True,
        )
        yield
        get_settings.cache_clear()


@pytest.fixture(scope="module")
def database_url() -> str:
    """URL asyncpg de un PostgreSQL temporal con Testcontainers."""

    with PostgresContainer("postgres:16-alpine") as postgres:
        raw = postgres.get_connection_url()
        yield raw.replace("+psycopg2", "").replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> Iterator[None]:
    """Aísla el limiter de slowapi (compartido por IP 'testclient' en todo el proceso)."""
    from app.infrastructure.adapters.primary.web.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
async def _dispose_infrastructure() -> AsyncIterator[None]:
    """Libera engine y cliente Redis en el mismo loop del test (asyncpg/redis son loop-affine)."""
    yield
    from app.infrastructure.adapters.secondary.persistence.database import (
        get_engine,
        get_sessionmaker,
    )
    from app.infrastructure.di.containers import (
        clear_application_caches,
        get_cache_port,
        get_redis_client,
        get_repository_health_port,
    )

    if get_engine.cache_info().currsize:
        await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    clear_application_caches()
    if get_redis_client.cache_info().currsize:
        await get_redis_client().aclose()
    get_redis_client.cache_clear()
    get_repository_health_port.cache_clear()
    get_cache_port.cache_clear()
