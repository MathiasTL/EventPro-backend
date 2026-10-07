"""Utilidades compartidas por las pruebas de integración."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID, uuid4

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from alembic import command
from app.core.security import hash_password
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.seed import seed

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HASHED_PASSWORD = hash_password("PasswordSeguro123!")


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


async def insert_user(engine: AsyncEngine, role_code: str) -> UUID:
    """Crea una cuenta activa con el rol indicado (el auth fresco exige cuenta en BD)."""

    email = f"user-{uuid4().hex[:12]}@eventpro.pe"
    phone = f"+519{uuid4().int % 10**8:08d}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO roles (code, name) VALUES "
                "('SUPERADMIN', 'Superadministrador'), "
                "('ENCARGADO', 'Encargado'), "
                "('OPERADOR', 'Operador') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        user_id = await connection.scalar(
            text(
                "INSERT INTO users (role_id, full_name, email, phone, hashed_password) "
                "SELECT id, 'Usuario de prueba', :email, :phone, :password "
                "FROM roles WHERE code = :role RETURNING id"
            ),
            {"email": email, "phone": phone, "password": _HASHED_PASSWORD, "role": role_code},
        )
    if user_id is None:
        raise RuntimeError(f"Rol desconocido para insert_user: {role_code}")
    return user_id
