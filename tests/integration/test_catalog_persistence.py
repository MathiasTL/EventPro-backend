"""Prueba de integración: migración Alembic + seed sobre PostgreSQL real.

Usa Testcontainers (Docker) y está marcada como ``integration``; no se ejecuta con el
``pytest`` por defecto. Para correrla::

    pytest -m integration

Verifica que el esquema del catálogo se crea, que el seed es idempotente y que los
conteos coinciden con ``Docs/03-datos/03-estrategia-migraciones-y-seeds.md``.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    InventoryItemModel,
    PackageInventoryItemModel,
    PackageModel,
)
from app.infrastructure.adapters.secondary.persistence.seed import seed

from ._support import run_migrations

pytestmark = pytest.mark.integration


def test_migration_and_seed(database_url: str) -> None:
    run_migrations(database_url)

    async def _exercise() -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                first = await seed(session)
                await session.commit()
            async with factory() as session:
                second = await seed(session)
                await session.commit()
            async with factory() as session:
                packages = (
                    await session.execute(select(func.count()).select_from(PackageModel))
                ).scalar_one()
                inventory = (
                    await session.execute(select(func.count()).select_from(InventoryItemModel))
                ).scalar_one()
                links = (
                    await session.execute(
                        select(func.count()).select_from(PackageInventoryItemModel)
                    )
                ).scalar_one()
            return first, second, {"packages": packages, "inventory": inventory, "links": links}
        finally:
            await engine.dispose()

    first, second, totals = asyncio.run(_exercise())

    assert first["packages"] == 8
    assert first["themes"] == 5
    assert first["extras"] == 6
    assert first["inventory_items"] == 2
    assert first["package_inventory_items"] == 2

    # Idempotencia: la segunda ejecución no crea nada nuevo.
    assert all(value == 0 for value in second.values())

    assert totals == {"packages": 8, "inventory": 2, "links": 2}
