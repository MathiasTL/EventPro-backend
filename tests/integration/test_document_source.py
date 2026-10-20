"""StorageDocumentSource sobre PostgreSQL 16 real: lee booking_documents."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.storage.document_source_adapter import (
    StorageDocumentSource,
)
from app.infrastructure.adapters.secondary.storage.postgres_booking_documents import (
    PostgresBookingDocuments,
)

from ._support import run_migrations

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


@pytest.fixture(scope="module")
def migrated_url(database_url: str) -> str:
    run_migrations(database_url)
    return database_url


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_reads_a_document_stored_in_the_database(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session, session.begin():
        path = await PostgresBookingDocuments(session).store(
            data=PDF, content_type="application/pdf", original_filename="contrato.pdf"
        )

    assert path.startswith("database/contracts/")
    assert await StorageDocumentSource(factory).read(path) == PDF


async def test_a_missing_database_document_raises_not_found(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await StorageDocumentSource(factory).read(f"database/contracts/{uuid4()}")
