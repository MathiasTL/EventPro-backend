"""Clients, quotes y quote_extras sobre PostgreSQL 16 real (sin migración nueva)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.entities.quote import QuoteSource, QuoteStatus
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.mobility import RouteEstimate
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.models import Base
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_client_repository import (  # noqa: E501
    SqlAlchemyClientRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_quote_repository import (  # noqa: E501
    SqlAlchemyQuoteRepository,
)
from tests.domain.financial_support import pen
from tests.domain.quote_support import NOW, make_quote

from ._support import run_migrations

pytestmark = pytest.mark.integration


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


def _phone() -> str:
    return f"9{uuid4().int % 10**8:08d}"


async def _seed_catalog(engine: AsyncEngine, extras: int = 1) -> tuple[UUID, list[UUID]]:
    async with engine.begin() as connection:
        package_id = await connection.scalar(
            text(
                "INSERT INTO packages (name, service_category, base_price, direct_cost) "
                "VALUES ('Paquete de prueba', 'SHOW', 1000, 400) RETURNING id"
            )
        )
        extra_ids = [
            await connection.scalar(
                text(
                    "INSERT INTO extras (name, sale_price, direct_cost) "
                    "VALUES (:name, 50.25, 20) RETURNING id"
                ),
                {"name": f"Extra {index}"},
            )
            for index in range(extras)
        ]
    assert package_id is not None
    return package_id, sorted(extra_ids)


async def _new_client(factory: async_sessionmaker[AsyncSession]) -> UUID:
    async with factory() as session:
        client = await SqlAlchemyClientRepository(session).get_or_create(_phone(), "Cliente")
        await session.commit()
    return client.id


async def test_quote_round_trip_preserves_money_and_extras_exactly(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    package_id, [extra_id] = await _seed_catalog(engine)
    client_id = await _new_client(factory)
    quote = make_quote(
        client_id=client_id,
        package_id=package_id,
        extra_id=extra_id,
        estimate=RouteEstimate(Decimal("12.345"), 33),
        latitude=Decimal("-12.1211234"),
        longitude=Decimal("-77.0301234"),
    )
    async with factory() as session:
        await SqlAlchemyQuoteRepository(session).add(quote)
        await session.commit()
    async with factory() as session:
        loaded = await SqlAlchemyQuoteRepository(session).get_by_id(quote.id)
    assert loaded == quote
    assert loaded is not None
    assert loaded.calculated_distance_km == Decimal("12.35")  # 12.345 cuantizado HALF_UP
    assert loaded.liquidation.total_amount == quote.liquidation.total_amount
    assert loaded.liquidation.pending_balance == quote.liquidation.pending_balance
    assert loaded.extras[0].subtotal == pen("150.75")
    assert loaded.sent_at.utcoffset() == timedelta(0)


async def test_contingency_quote_keeps_null_distance_and_minutes(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    package_id, [extra_id] = await _seed_catalog(engine)
    quote = make_quote(
        client_id=await _new_client(factory), package_id=package_id, extra_id=extra_id
    )
    async with factory() as session:
        await SqlAlchemyQuoteRepository(session).add(quote)
        await session.commit()
        row = (
            (
                await session.execute(
                    text(
                        "SELECT calculated_distance_km, calculated_transit_minutes, "
                        "base_mobility_amount, final_mobility_amount FROM quotes WHERE id = :id"
                    ),
                    {"id": quote.id},
                )
            )
            .mappings()
            .one()
        )
    assert row["calculated_distance_km"] is None
    assert row["calculated_transit_minutes"] is None
    assert row["base_mobility_amount"] == Decimal("45.00")
    assert row["final_mobility_amount"] == Decimal("45.00")


async def test_exempt_quote_round_trips_zero_mobility(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    package_id, [extra_id] = await _seed_catalog(engine)
    quote = make_quote(
        client_id=await _new_client(factory),
        package_id=package_id,
        extra_id=extra_id,
        client_provides_mobility=True,
    )
    async with factory() as session:
        await SqlAlchemyQuoteRepository(session).add(quote)
        await session.commit()
    async with factory() as session:
        loaded = await SqlAlchemyQuoteRepository(session).get_by_id(quote.id)
    assert loaded == quote
    assert loaded is not None
    assert loaded.client_provides_mobility is True
    assert loaded.liquidation.mobility_amount == pen("0.00")


async def test_save_persists_state_transitions(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    package_id, [extra_id] = await _seed_catalog(engine)
    quote = make_quote(
        client_id=await _new_client(factory), package_id=package_id, extra_id=extra_id
    )
    async with factory() as session:
        repo = SqlAlchemyQuoteRepository(session)
        await repo.add(quote)
        await session.commit()
    async with factory() as session:
        repo = SqlAlchemyQuoteRepository(session)
        loaded = await repo.get_by_id(quote.id)
        assert loaded is not None
        loaded.start_payment(NOW)
        await repo.save(loaded)
        await session.commit()
    async with factory() as session:
        reloaded = await SqlAlchemyQuoteRepository(session).get_by_id(quote.id)
    assert reloaded is not None
    assert reloaded.status is QuoteStatus.PAYMENT_STARTED
    assert reloaded.extras == quote.extras


async def test_save_unknown_quote_raises_not_found(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        with pytest.raises(ResourceNotFoundError):
            await SqlAlchemyQuoteRepository(session).save(make_quote())


async def test_repositories_never_commit(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    package_id, [extra_id] = await _seed_catalog(engine)
    client_id = await _new_client(factory)
    quote = make_quote(client_id=client_id, package_id=package_id, extra_id=extra_id)
    phone = _phone()
    async with factory() as writer, factory() as reader:
        await SqlAlchemyQuoteRepository(writer).add(quote)
        created = await SqlAlchemyClientRepository(writer).get_or_create(phone, "Sin commit")
        assert await SqlAlchemyQuoteRepository(reader).get_by_id(quote.id) is None
        assert await SqlAlchemyClientRepository(reader).get_by_id(created.id) is None
        await writer.rollback()
        assert await SqlAlchemyQuoteRepository(reader).get_by_id(quote.id) is None
        await SqlAlchemyQuoteRepository(writer).add(quote)
        await writer.commit()
        assert await SqlAlchemyQuoteRepository(reader).get_by_id(quote.id) == quote


async def test_manual_request_hash_is_unique_only_for_started_or_converted(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    package_id, [extra_id] = await _seed_catalog(engine)
    client_id = await _new_client(factory)
    digest = "b" * 64

    def manual(**changes: object):  # type: ignore[no-untyped-def]
        return make_quote(
            client_id=client_id,
            package_id=package_id,
            extra_id=extra_id,
            source=QuoteSource.MANUAL,
            manual_request_hash=digest,
            **changes,
        )

    started = manual()
    started.start_payment(NOW)
    async with factory() as session:
        repo = SqlAlchemyQuoteRepository(session)
        await repo.add(started)
        await repo.add(manual())  # SENT: fuera del predicado del índice parcial
        await session.commit()
    duplicate = manual()
    duplicate.start_payment(NOW)
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await SqlAlchemyQuoteRepository(session).add(duplicate)
        await session.rollback()


async def test_legacy_manual_row_loads_without_recomputing_balance(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    package_id, _ = await _seed_catalog(engine, extras=0)
    client_id = await _new_client(factory)
    quote_id = uuid4()
    async with engine.begin() as connection:
        # Fila del flujo manual (PR #22): pending_balance omite la movilidad (spec 06, sección 5).
        await connection.execute(
            text(
                "INSERT INTO quotes (id, client_id, source, event_date, event_time, "
                "location_address, location_district, package_id, services_subtotal, "
                "total_amount, advance_amount, pending_balance, status, sent_at, expires_at, "
                "base_mobility_amount, final_mobility_amount, manual_request_hash) "
                "VALUES (:id, :client, 'MANUAL', '2026-10-25', '21:30', 'Av. Benavides 1', "
                "'Miraflores', :package, 1000, 1080.50, 100, 900, 'PAYMENT_STARTED', now(), "
                "now() + interval '24 hours', 80.50, 80.50, :hash)"
            ),
            {"id": quote_id, "client": client_id, "package": package_id, "hash": "c" * 64},
        )
    async with factory() as session:
        loaded = await SqlAlchemyQuoteRepository(session).get_by_id(quote_id)
    assert loaded is not None
    assert loaded.source is QuoteSource.MANUAL
    assert loaded.status is QuoteStatus.PAYMENT_STARTED
    assert loaded.liquidation.pending_balance == pen("900.00")
    assert loaded.liquidation.mobility_amount == pen("80.50")
    assert loaded.calculated_distance_km == Decimal("0.00")  # server_default de la tabla
    assert loaded.extras == ()


async def test_get_or_create_deduplicates_phone_formats_and_keeps_name(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    local = _phone()
    async with factory() as session:
        repo = SqlAlchemyClientRepository(session)
        first = await repo.get_or_create(local, "Ana Torres")
        same = await repo.get_or_create(f"+51 {local[:3]}-{local[3:6]}-{local[6:]}", "Otro Nombre")
        again = await repo.get_or_create(f"51{local}", "Y otro más")
        await session.commit()
    assert first.phone.value == f"+51{local}"
    assert first.full_name == "Ana Torres"
    assert same.id == again.id == first.id
    assert same.full_name == "Ana Torres"
    async with factory() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM clients WHERE phone LIKE :suffix"),
            {"suffix": f"%{local}"},
        )
    assert count == 1


async def test_get_by_phone_finds_legacy_formats_and_prefers_canonical(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    legacy_only = _phone()
    both = _phone()
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO clients (phone, full_name) VALUES (:p, 'Heredado')"),
            {"p": f"51{legacy_only}"},
        )
        await connection.execute(
            text("INSERT INTO clients (phone, full_name) VALUES (:p, 'Local')"), {"p": both}
        )
        await connection.execute(
            text("INSERT INTO clients (phone, full_name) VALUES (:p, 'Canónico')"),
            {"p": f"+51{both}"},
        )
    async with factory() as session:
        repo = SqlAlchemyClientRepository(session)
        legacy = await repo.get_by_phone(f"+51 {legacy_only}")
        assert legacy is not None
        assert legacy.full_name == "Heredado"
        assert legacy.phone.value == f"+51{legacy_only}"  # el mapper normaliza al leer
        assert (await repo.get_or_create(legacy_only, "Nuevo")).id == legacy.id
        canonical = await repo.get_by_phone(both)
        assert canonical is not None
        assert canonical.full_name == "Canónico"
        assert await repo.get_by_phone(_phone()) is None


async def test_client_loads_dni_and_ruc_and_rejects_invalid_phone(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> None:
    phone = _phone()
    async with engine.begin() as connection:
        client_id = await connection.scalar(
            text(
                "INSERT INTO clients (phone, full_name, dni, ruc) "
                "VALUES (:p, 'Con documentos', '12345678', '20123456789') RETURNING id"
            ),
            {"p": f"+51{phone}"},
        )
    async with factory() as session:
        repo = SqlAlchemyClientRepository(session)
        loaded = await repo.get_by_id(client_id)
        assert loaded is not None
        assert (loaded.dni, loaded.ruc) == ("12345678", "20123456789")
        assert await repo.get_by_id(uuid4()) is None
        with pytest.raises(ValidationError):
            await repo.get_or_create("12345", "Inválido")
        with pytest.raises(ValidationError):
            await repo.get_by_phone("no-es-telefono")


async def test_concurrent_get_or_create_creates_a_single_client(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    phone = _phone()

    async def create(name: str) -> UUID:
        async with factory() as session:
            client = await SqlAlchemyClientRepository(session).get_or_create(phone, name)
            await session.commit()
            return client.id

    first, second = await asyncio.gather(create("Primero"), create("Segundo"))
    assert first == second


async def test_orm_models_match_the_alembic_schema(engine: AsyncEngine) -> None:
    scope = {"clients", "quotes", "quote_extras"}

    def in_scope(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object):
        table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
        return table in scope

    def diff(connection) -> list[object]:  # type: ignore[no-untyped-def]
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "include_object": in_scope}
        )
        return compare_metadata(context, Base.metadata)

    async with engine.connect() as connection:
        differences = await connection.run_sync(diff)
    assert differences == []
