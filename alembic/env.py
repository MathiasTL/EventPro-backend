"""Entorno de Alembic para EventPro (PostgreSQL + asyncpg).

La URL se toma de la variable ``DATABASE_URL`` (configuración global) salvo que el
llamador la fije explícitamente con ``config.set_main_option('sqlalchemy.url', ...)``,
lo que permite apuntar las pruebas de integración a un contenedor temporal.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings

# Importar los modelos para poblar Base.metadata (autogenerate y create_all).
from app.infrastructure.adapters.secondary.persistence.models import (  # noqa: F401
    audit_log,
    catalog_models,
    client_model,
    event_extension_model,
    event_model,
    payment_model,
    quote_model,
    refresh_token,
    role,
    user,
)
from app.infrastructure.adapters.secondary.persistence.models.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    """Skip database objects that have no ORM model yet.

    The baseline creates every documented table, but each epic adds its model later.
    Without this filter autogenerate would propose dropping those tables (and the
    foreign keys that point to them from modeled tables). Modeled tables are compared
    normally.
    """

    if type_ == "table" and reflected and compare_to is None:
        return name in target_metadata.tables
    if type_ == "foreign_key_constraint" and reflected and compare_to is None:
        return obj.referred_table.name in target_metadata.tables
    return True


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse a la base de datos."""

    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
