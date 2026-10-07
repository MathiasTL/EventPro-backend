"""Conexión asíncrona a PostgreSQL con SQLAlchemy 2.0 y asyncpg."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def build_engine(database_url: str | None = None) -> AsyncEngine:
    """Crea un motor asíncrono para la URL indicada (o la configuración global)."""

    return create_async_engine(
        database_url or get_settings().database_url,
        echo=False,
        pool_pre_ping=True,
        future=True,
    )


def build_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Crea una fábrica de sesiones asíncrona."""

    return async_sessionmaker(
        bind=build_engine(database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )


@lru_cache
def get_engine() -> AsyncEngine:
    """Motor global (cachéado) usado por los contenedores de la aplicación."""
    return build_engine()


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Fábrica de sesiones global (cachéada) sobre :func:`get_engine`."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI que entrega una sesión por petición."""

    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
