"""Fixtures compartidas de las pruebas de integración.

``database_url`` levanta un PostgreSQL 16 real con Testcontainers. El alcance
``module`` garantiza un contenedor limpio por cada módulo de prueba.
"""

from __future__ import annotations

import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="module")
def database_url() -> str:
    """URL asyncpg de un PostgreSQL temporal con Testcontainers."""

    with PostgresContainer("postgres:16-alpine") as postgres:
        raw = postgres.get_connection_url()
        yield raw.replace("+psycopg2", "").replace("postgresql://", "postgresql+asyncpg://")
