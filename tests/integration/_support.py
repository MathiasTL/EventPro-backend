"""Utilidades compartidas por las pruebas de integración."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.seed import seed

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_migrations(database_url: str) -> None:
    """Aplica todas las migraciones de Alembic contra la base indicada."""

    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def seed_database(database_url: str) -> dict[str, int]:
    """Ejecuta el seed idempotente y confirma la transacción."""

    async def _run() -> dict[str, int]:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                counts = await seed(session)
                await session.commit()
                return counts
        finally:
            await engine.dispose()

    return asyncio.run(_run())
