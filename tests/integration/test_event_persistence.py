"""Esquema events sobre PostgreSQL 16: integridad, FK consumibles y reversibilidad."""

import asyncio

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from alembic import command
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from tests.event_support import make_event

pytestmark = pytest.mark.integration


def test_events_upgrade_constraints_and_downgrade(database_url: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    scripts = ScriptDirectory.from_config(config)
    assert len(scripts.get_heads()) == 1
    assert scripts.get_revision("0004_events").down_revision == "0003_auth_audit_tables"
    command.upgrade(config, "0003_auth_audit_tables")
    command.upgrade(config, "head")

    async def exercise() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                columns = await connection.run_sync(
                    lambda conn: inspect(conn).get_columns("events")
                )
                assert {column["name"] for column in columns} == {
                    "id",
                    "event_code",
                    "quote_id",
                    "event_date",
                    "start_time",
                    "end_time",
                    "address",
                    "district",
                    "client_observations",
                    "status",
                    "total_services_amount",
                    "total_mobility_amount",
                    "final_total_amount",
                    "advance_paid",
                    "pre_show_balance_paid",
                    "extra_hours_amount",
                    "created_at",
                    "actual_start_time",
                }
                assert (
                    await connection.run_sync(lambda conn: inspect(conn).get_foreign_keys("events"))
                    == []
                )
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                assert not {"quotes", "clients", "crew_assignments"}.intersection(tables)
                indexes = await connection.run_sync(
                    lambda conn: inspect(conn).get_indexes("events")
                )
                assert {"ix_events_event_date", "ix_events_district"} <= {
                    i["name"] for i in indexes
                }
                result = await connection.execute(
                    text(
                        "INSERT INTO events (event_code, quote_id, event_date, start_time, "
                        "end_time, address, district, total_services_amount, "
                        "total_mobility_amount, final_total_amount) "
                        "VALUES ('EVT-DEFAULT', gen_random_uuid(), '2026-10-15', '21:30', '22:30', "
                        "'Av. Benavides', 'Miraflores', 980, 100.50, 1080.50) RETURNING *"
                    )
                )
                row = result.mappings().one()
                assert row["id"] is not None
                assert row["status"] == "AWAITING_SIGNATURE"
                assert row["client_observations"] is None
                assert (
                    row["advance_paid"]
                    == row["pre_show_balance_paid"]
                    == row["extra_hours_amount"]
                    == 0
                )
                assert row["created_at"].tzinfo is not None
                # Simula consumidores de events.id sin crear tablas de otras épicas.
                await connection.execute(
                    text("CREATE TABLE event_fk_probe (event_id UUID REFERENCES events(id))")
                )
                await connection.execute(
                    text("INSERT INTO event_fk_probe VALUES (:id)"), {"id": row["id"]}
                )
                await connection.execute(text("DROP TABLE event_fk_probe"))

            factory = async_sessionmaker(engine, expire_on_commit=False)
            original = make_event()
            async with factory() as session:
                session.add(event_to_model(original))
                await session.commit()
            for changes in (
                {"event_code": original.event_code},
                {"quote_id": original.quote_id},
                {"status": "INVALID"},
                {"quote_id": None},
            ):
                async with factory() as session:
                    row = event_to_model(make_event())
                    for key, value in changes.items():
                        setattr(row, key, value)
                    session.add(row)
                    with pytest.raises(IntegrityError):
                        await session.commit()
                    await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    command.downgrade(config, "0003_auth_audit_tables")

    async def check_removed() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                assert not await connection.run_sync(lambda conn: inspect(conn).has_table("events"))
                assert await connection.run_sync(lambda conn: inspect(conn).has_table("users"))
        finally:
            await engine.dispose()

    asyncio.run(check_removed())
    command.upgrade(config, "head")
