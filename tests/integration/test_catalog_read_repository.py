"""Prueba de integración del repositorio de lectura del catálogo.

Seeds reales + consultas del ``SqlAlchemyCatalogReadRepository`` sobre PostgreSQL con
Testcontainers. Marcada como ``integration``; correr con ``pytest -m integration``.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.value_objects.service_category import ServiceCategory
from app.infrastructure.adapters.secondary.persistence import SqlAlchemyCatalogReadRepository
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    PackageThemeModel,
)

from ._support import run_migrations, seed_database

pytestmark = pytest.mark.integration

_EXPECTED_PACKAGES = {
    "Hora Loca Básica",
    "Hora Loca Medium",
    "Hora Loca Premium",
    "Show Infantil Divertido",
    "Paquete Baby Shower Especial",
    "Servicio de DJ y Luces Pro",
    "Ambientación y Toldos Estándar",
    "Combo Full Fiesta (Hora Loca + DJ)",
}


def test_catalog_read_repository(database_url: str) -> None:
    run_migrations(database_url)
    seed_database(database_url)

    async def _exercise() -> None:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                repo = SqlAlchemyCatalogReadRepository(session)

                packages = await repo.list_packages()
                assert {p.name for p in packages} == _EXPECTED_PACKAGES

                medium = next(p for p in packages if p.name == "Hora Loca Medium")
                assert medium.base_price == Decimal("750.00")
                assert medium.service_category is ServiceCategory.SHOW
                assert medium.duration_minutes == 60
                assert medium.compatible_themes == ()

                assert await repo.get_package(uuid4()) is None

                themes = await repo.list_themes()
                assert len(themes) == 5
                selva = next(t for t in themes if t.name == "Selva Salvaje (Safari)")
                assert await repo.get_theme(uuid4()) is None

                extras = await repo.list_extras()
                assert len(extras) == 6
                assert all(extra.sale_price > 0 for extra in extras)

                tents = next(p for p in packages if p.name == "Ambientación y Toldos Estándar")
                requirements = await repo.get_inventory_requirements(tents.id)
                assert {r.name for r in requirements} == {
                    "Toldo Estándar 3x3 m",
                    "Kit de Ambientación Estándar",
                }
                assert all(r.quantity == 1 for r in requirements)
                assert await repo.get_inventory_requirements(medium.id) == ()

                # Compatibilidad paquete ↔ temática.
                assert not await repo.are_themes_compatible(medium.id, selva.id)
                session.add(PackageThemeModel(package_id=medium.id, theme_id=selva.id))
                await session.commit()
                assert await repo.are_themes_compatible(medium.id, selva.id)

                # La desactivación de un extra se refleja en la lectura.
                extra_row = await session.get(ExtraModel, extras[0].id)
                assert extra_row is not None
                extra_row.is_active = False
                await session.commit()
                assert len(await repo.list_extras()) == 5
                assert len(await repo.list_extras(include_inactive=True)) == 6

            # Sesión nueva: comprueba que las temáticas compatibles se cargan del
            # repositorio (no de la caché de identidad de la sesión anterior).
            async with factory() as session:
                reloaded = await SqlAlchemyCatalogReadRepository(session).get_package(medium.id)
                assert reloaded is not None
                assert [t.name for t in reloaded.compatible_themes] == ["Selva Salvaje (Safari)"]
        finally:
            await engine.dispose()

    asyncio.run(_exercise())
