"""Utilidades compartidas por las pruebas de integración."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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


async def insert_quotes(engine: AsyncEngine, quote_ids: Iterable[UUID]) -> None:
    """Crea las cotizaciones (con su cliente y paquete) que las FK de events/payments exigen."""

    async with engine.begin() as connection:
        package_id = await connection.scalar(
            text(
                "INSERT INTO packages (name, service_category, base_price, direct_cost) "
                "VALUES ('Paquete de prueba', 'SHOW', 100, 50) RETURNING id"
            )
        )
        client_id = await connection.scalar(
            text(
                "INSERT INTO clients (phone, full_name) "
                "VALUES ('+51' || substr(md5(random()::text), 1, 9), 'Cliente de prueba') "
                "RETURNING id"
            )
        )
        for quote_id in quote_ids:
            await connection.execute(
                text(
                    "INSERT INTO quotes (id, client_id, event_date, event_time, "
                    "location_address, location_district, package_id, services_subtotal, "
                    "total_amount, advance_amount, pending_balance, sent_at, expires_at) "
                    "VALUES (:id, :client_id, '2026-10-15', '21:30', 'Av. Benavides', "
                    "'Miraflores', :package_id, 100, 100, 10, 90, now(), now())"
                ),
                {"id": quote_id, "client_id": client_id, "package_id": package_id},
            )
