"""Conexión asíncrona a PostgreSQL con SQLAlchemy 2.0 y asyncpg."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def build_engine(database_url: str | None = None) -> AsyncEngine:
    """Crea un motor asíncrono para la URL indicada (o la configuración global)."""

    return create_async_engine(
        database_url or settings.database_url,
        echo=False,
        pool_pre_ping=True,
        future=True,
    )


def build_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Crea una fábrica de sesiones asíncronas."""

    return async_sessionmaker(
        bind=build_engine(database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )


engine: AsyncEngine = build_engine()
SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI que entrega una sesión por petición."""

    async with SessionFactory() as session:
        yield session
