"""Migración 0004_outbox_delivery_tracking sobre PostgreSQL 16 real (upgrade y downgrade)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.infrastructure.adapters.secondary.persistence.database import build_engine

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_NEW_COLUMNS = {
    "external_message_id",
    "conversation_id",
    "delivery_status",
    "delivery_error",
    "delivered_at",
    "read_at",
    "redact_after_send",
}


def _config(database_url: str) -> Config:
    config = Config(str(_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _run(database_url: str, work: Callable[..., Awaitable[Any]]) -> Any:
    async def runner() -> Any:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                return await work(connection)
        finally:
            await engine.dispose()

    return asyncio.run(runner())


async def _columns(connection) -> set[str]:  # type: ignore[no-untyped-def]
    names = await connection.run_sync(
        lambda sync: {c["name"] for c in inspect(sync).get_columns("outbox_messages")}
    )
    return set(names)


async def _max_attempts_default(connection) -> str:  # type: ignore[no-untyped-def]
    return str(
        await connection.scalar(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'outbox_messages' AND column_name = 'max_attempts'"
            )
        )
    )


async def _insert(connection, phone: str) -> int:  # type: ignore[no-untyped-def]
    return int(
        await connection.scalar(
            text(
                "INSERT INTO outbox_messages (recipient_phone, message_type, payload) "
                "VALUES (:phone, 'TEXT', '{\"body\": \"hola\"}') RETURNING max_attempts"
            ),
            {"phone": phone},
        )
    )


def test_revision_chain_is_linear_from_0003() -> None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_config("postgresql+asyncpg://unused"))
    revision = script.get_revision("0004_outbox_delivery_tracking")
    assert revision is not None
    assert revision.down_revision == "0003_manual_booking_documents"
    assert len(script.get_heads()) == 1
    financial_revision = script.get_revision("0005_event_financial_snapshots")
    assert financial_revision is not None
    assert financial_revision.down_revision == revision.revision


def test_upgrade_adds_columns_and_default_and_downgrade_restores_them(database_url: str) -> None:
    config = _config(database_url)
    command.upgrade(config, "0003_manual_booking_documents")

    async def legacy_row(connection) -> int:  # type: ignore[no-untyped-def]
        assert not _NEW_COLUMNS & await _columns(connection)
        assert "5" in await _max_attempts_default(connection)
        return await _insert(connection, "+51999000111")

    assert _run(database_url, legacy_row) == 5

    command.upgrade(config, "0004_outbox_delivery_tracking")

    async def after_upgrade(connection) -> None:  # type: ignore[no-untyped-def]
        assert await _columns(connection) >= _NEW_COLUMNS
        assert "6" in await _max_attempts_default(connection)
        legacy = await connection.execute(
            text(
                "SELECT max_attempts, redact_after_send, external_message_id, delivery_status "
                "FROM outbox_messages WHERE recipient_phone = '+51999000111'"
            )
        )
        assert tuple(legacy.one()) == (5, False, None, None)  # no se reescriben filas existentes
        assert await _insert(connection, "+51999000222") == 6

    _run(database_url, after_upgrade)

    command.downgrade(config, "0003_manual_booking_documents")

    async def after_downgrade(connection) -> None:  # type: ignore[no-untyped-def]
        assert not _NEW_COLUMNS & await _columns(connection)
        assert "5" in await _max_attempts_default(connection)
        count = await connection.scalar(text("SELECT count(*) FROM outbox_messages"))
        assert count == 2  # el downgrade conserva los mensajes

    _run(database_url, after_downgrade)

    command.upgrade(config, "head")
    _run(database_url, lambda connection: _check_head(connection))


async def _check_head(connection) -> None:  # type: ignore[no-untyped-def]
    assert await _columns(connection) >= _NEW_COLUMNS


def test_new_constraints_reject_duplicates_and_unknown_delivery_status(database_url: str) -> None:
    command.upgrade(_config(database_url), "head")

    async def duplicate_external_id(connection) -> None:  # type: ignore[no-untyped-def]
        statement = text(
            "INSERT INTO outbox_messages (recipient_phone, message_type, external_message_id) "
            "VALUES (:phone, 'TEXT', 'cw-dup')"
        )
        await connection.execute(statement, {"phone": "+51999000333"})
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(statement, {"phone": "+51999000444"})

    _run(database_url, duplicate_external_id)

    async def several_without_external_id(connection) -> None:  # type: ignore[no-untyped-def]
        await _insert(connection, "+51999000555")
        await _insert(connection, "+51999000666")  # NULL no choca con UNIQUE

    _run(database_url, several_without_external_id)

    async def unknown_delivery_status(connection) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO outbox_messages "
                        "(recipient_phone, message_type, delivery_status) "
                        "VALUES ('+51999000777', 'TEXT', 'LOST')"
                    )
                )
        await connection.execute(
            text(
                "INSERT INTO outbox_messages (recipient_phone, message_type, delivery_status) "
                "VALUES ('+51999000888', 'TEXT', 'READ')"
            )
        )

    _run(database_url, unknown_delivery_status)
