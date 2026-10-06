"""Tests del repositorio de pagos contra PostgreSQL real (Testcontainers)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dtos.payment_dto import PaymentFilterDTO
from app.domain.entities.payment import Payment, PaymentConcept, PaymentMethod
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_payment_repository import (  # noqa: E501
    SqlAlchemyPaymentRepository,
)

from ._support import run_migrations

pytestmark = pytest.mark.integration


def test_payment_repository_roundtrip(database_url: str) -> None:
    run_migrations(database_url)

    async def _exercise() -> tuple[int, PaymentConcept, int]:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            payment = Payment(
                quote_id=uuid4(),
                concept=PaymentConcept.ADVANCE,
                payment_method=PaymentMethod.YAPE,
                amount=Money(Decimal("120.00")),
                evidence_path="evidence/receipt.png",
            )
            async with factory() as session:
                repo = SqlAlchemyPaymentRepository(session)
                await repo.save(payment)
                await session.commit()
            async with factory() as session:
                repo = SqlAlchemyPaymentRepository(session)
                loaded = await repo.get(payment.id)
                total = await repo.count(PaymentFilterDTO())
                assert loaded is not None
                return total, loaded.concept, (loaded.amount.amount == Decimal("120.00"))
        finally:
            await engine.dispose()

    total, concept, amount_ok = asyncio.run(_exercise())
    assert total == 1
    assert concept == PaymentConcept.ADVANCE
    assert bool(amount_ok) is True
