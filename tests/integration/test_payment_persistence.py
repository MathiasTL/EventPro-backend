"""Esquema payments sobre PostgreSQL 16: integridad, FK a quotes/events/users y reversibilidad."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from alembic import command
from app.domain.entities.payment import (
    Payment,
    PaymentConcept,
    PaymentMethod,
)
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.mappers.payment_mapper import (
    payment_to_model,
)
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_payment_repository import (  # noqa: E501
    SqlAlchemyPaymentRepository,
)

from ._support import insert_quotes

pytestmark = pytest.mark.integration


def _advance(**changes) -> Payment:
    values: dict = {
        "quote_id": uuid4(),
        "concept": PaymentConcept.ADVANCE,
        "payment_method": PaymentMethod.YAPE,
        "amount": Money(Decimal("100.00")),
        "evidence_path": "evidence/receipt.png",
    }
    values.update(changes)
    return Payment(**values)


def test_payments_upgrade_constraints_and_downgrade(database_url: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    scripts = ScriptDirectory.from_config(config)
    assert len(scripts.get_heads()) == 1
    assert scripts.get_revision("0001_initial_schema").down_revision is None
    command.upgrade(config, "head")

    async def exercise() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                columns = await connection.run_sync(
                    lambda conn: inspect(conn).get_columns("payments")
                )
                assert {column["name"] for column in columns} == {
                    "id",
                    "quote_id",
                    "event_id",
                    "concept",
                    "payment_method",
                    "amount",
                    "evidence_path",
                    "transaction_reference",
                    "validation_status",
                    "rejection_reason",
                    "verified_by_user_id",
                    "verified_at",
                    "registered_by_user_id",
                    "audit_status",
                    "audited_by_user_id",
                    "audited_at",
                    "audit_notes",
                    "created_at",
                }
                foreign_keys = await connection.run_sync(
                    lambda conn: inspect(conn).get_foreign_keys("payments")
                )
                referred = {fk["referred_table"] for fk in foreign_keys}
                assert {"quotes", "events", "users"} <= referred
            default_quote_id = uuid4()
            await insert_quotes(engine, [default_quote_id])
            async with engine.begin() as connection:
                result = await connection.execute(
                    text(
                        "INSERT INTO payments (quote_id, concept, payment_method, amount, "
                        "evidence_path) VALUES (:quote_id, 'ADVANCE', 'YAPE', 100.00, "
                        "'evidence/receipt.png') RETURNING *"
                    ),
                    {"quote_id": default_quote_id},
                )
                row = result.mappings().one()
                assert row["validation_status"] == "PENDING_VERIFICATION"
                assert row["audit_status"] is None
                assert row["created_at"].tzinfo is not None

            factory = async_sessionmaker(engine, expire_on_commit=False)
            original = _advance()
            await insert_quotes(engine, [original.quote_id])
            async with factory() as session:
                session.add(payment_to_model(original))
                await session.commit()
            async with factory() as session:
                loaded = await session.get(PaymentModel, original.id)
                assert loaded is not None
                assert loaded.validation_status == "PENDING_VERIFICATION"
            async with factory() as session:
                repo = SqlAlchemyPaymentRepository(session)
                pipeline = await repo.get_by_id(original.id)
                assert pipeline is not None
                assert pipeline.evidence_path == "evidence/receipt.png"
            for changes in (
                {"concept": "INVALID"},
                {"amount": Decimal("0.00")},
                {"audit_status": "REVIEWED"},
                {"quote_id": uuid4()},
            ):
                candidate = _advance()
                if "quote_id" not in changes:
                    await insert_quotes(engine, [candidate.quote_id])
                async with factory() as session:
                    row = payment_to_model(candidate)
                    for key, value in changes.items():
                        setattr(row, key, value)
                    session.add(row)
                    with pytest.raises(IntegrityError):
                        await session.commit()
                    await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    command.downgrade(config, "base")

    async def check_removed() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                has_payments = await connection.run_sync(
                    lambda conn: inspect(conn).has_table("payments")
                )
                assert not has_payments
                assert not await connection.run_sync(lambda conn: inspect(conn).has_table("events"))
                assert not await connection.run_sync(lambda conn: inspect(conn).has_table("users"))
        finally:
            await engine.dispose()

    asyncio.run(check_removed())
    command.upgrade(config, "head")
