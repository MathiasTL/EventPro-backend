"""Upgrade/downgrade en PostgreSQL efímero, preservando contratos previos."""

import asyncio
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from alembic import command
from app.infrastructure.adapters.secondary.persistence.database import build_engine

from ._support import insert_quotes

pytestmark = pytest.mark.integration


def test_contract_migration_is_linear_reversible_and_keeps_legacy_data(database_url):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    assert ScriptDirectory.from_config(config).get_heads() == ["0008_contract_signature"]
    command.upgrade(config, "0005_event_financial_snapshots")
    quote_id, event_id, contract_id = uuid4(), uuid4(), uuid4()

    async def seed():
        engine = build_engine(database_url)
        try:
            await insert_quotes(engine, [quote_id])
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO events(id,event_code,quote_id,event_date,start_time,end_time,"
                        "address,district,total_services_amount,total_mobility_amount,final_total_amount)"
                        "VALUES (:id,'MIGRATION',:quote,'2027-01-01','12:00','13:00',"
                        "'Lugar','Lima',100,0,100)"
                    ),
                    {"id": event_id, "quote": quote_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO contracts(id,contract_number,event_id,pdf_storage_path,status)"
                        "VALUES (:id,'CTR-2026-0042',:event,'legacy/document','ISSUED')"
                    ),
                    {"id": contract_id, "event": event_id},
                )
        finally:
            await engine.dispose()

    asyncio.run(seed())
    command.upgrade(config, "head")

    async def inspect_upgrade():
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                assert await connection.scalar(text("SELECT nextval('contract_number_seq')")) == 43
                assert (
                    await connection.scalar(
                        text("SELECT otp_request_count FROM contracts WHERE id=:id"),
                        {"id": contract_id},
                    )
                    == 0
                )
                assert (
                    await connection.scalar(
                        text("SELECT pdf_storage_path FROM contracts WHERE id=:id"),
                        {"id": contract_id},
                    )
                    == "legacy/document"
                )
        finally:
            await engine.dispose()

    asyncio.run(inspect_upgrade())
    command.downgrade(config, "0005_event_financial_snapshots")
    command.upgrade(config, "head")

    async def record_new_audit():
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO audit_logs(action,entity_name,entity_id) "
                        "VALUES ('CONTRACT_ISSUED','contracts',:id)"
                    ),
                    {"id": contract_id},
                )
        finally:
            await engine.dispose()

    asyncio.run(record_new_audit())
    with pytest.raises(RuntimeError, match="auditoría de contratos existente"):
        command.downgrade(config, "0005_event_financial_snapshots")
