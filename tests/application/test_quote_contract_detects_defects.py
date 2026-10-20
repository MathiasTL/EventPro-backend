"""Pruebas de mutación de la suite de contrato.

Una suite de contrato no tiene código de producción contra el que fallar primero, así que aquí
se prueba que de verdad detecta defectos: cada fake roto debe hacer fallar el caso del contrato
que protege esa regla (``AssertionError``).
"""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest

from app.application.dtos.quote_dto import CreatedQuoteDTO, CreateQuoteInput, PayAdvanceResultDTO
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import AvailabilityConflictError
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeCreateQuote,
    FakeExpireDueQuotes,
    FakePayAdvance,
    FakeScenario,
)

from .quote_ports_contract import (
    CreateQuoteContract,
    ExpireDueQuotesContract,
    PayAdvanceContract,
)
from .test_fake_quote_ports import FakeContractHooks


class _NaiveExpiryCreate(FakeCreateQuote):
    """Defecto: ``expires_at`` sin zona horaria."""

    async def execute(self, dto: CreateQuoteInput) -> CreatedQuoteDTO:
        created = await super().execute(dto)
        return replace(created, expires_at=created.expires_at.replace(tzinfo=None))


class _MissingAlternativesCreate(FakeCreateQuote):
    """Defecto: el conflicto de disponibilidad no lleva alternativas."""

    async def execute(self, dto: CreateQuoteInput) -> CreatedQuoteDTO:
        if self.scenario is FakeScenario.AVAILABILITY_CONFLICT:
            raise AvailabilityConflictError("Sin cupo.")
        return await super().execute(dto)


class _IgnoresPaymentInVerificationExpire(FakeExpireDueQuotes):
    """Defecto: vence también las cotizaciones con un pago en verificación."""

    async def execute(self) -> int:
        now = self._clock.utcnow()
        expired = 0
        for quote in self._store.quotes():
            if quote.status in (QuoteStatus.SENT, QuoteStatus.PAYMENT_STARTED) and (
                quote.expires_at <= now
            ):
                quote.status = QuoteStatus.EXPIRED
                expired += 1
        return expired


class _NotIdempotentPayAdvance(FakePayAdvance):
    """Defecto: cada llamada repetida extiende el plazo de pago."""

    async def execute(self, quote_id: Any) -> PayAdvanceResultDTO:
        already_started = self._store.get_quote(quote_id).status is QuoteStatus.PAYMENT_STARTED
        result = await super().execute(quote_id)
        if already_started:
            return replace(result, payment_deadline=result.payment_deadline + timedelta(hours=1))
        return result


class _BrokenCreateRun(FakeContractHooks, CreateQuoteContract):
    broken: type[FakeCreateQuote]

    def make_port(self) -> FakeCreateQuote:
        return self.broken(self.store, clock=self.clock)


class _BrokenExpireRun(FakeContractHooks, ExpireDueQuotesContract):
    def make_port(self) -> FakeExpireDueQuotes:
        return _IgnoresPaymentInVerificationExpire(self.store, clock=self.clock)


class _BrokenPayRun(FakeContractHooks, PayAdvanceContract):
    def make_port(self) -> FakePayAdvance:
        return _NotIdempotentPayAdvance(self.store, clock=self.clock)


class _NaiveExpiryRun(_BrokenCreateRun):
    broken = _NaiveExpiryCreate


class _MissingAlternativesRun(_BrokenCreateRun):
    broken = _MissingAlternativesCreate


async def _run(run_class: type, case: str) -> None:
    run = run_class()
    run.setup_method()
    check: Callable[[Any], Awaitable[None]] = getattr(run, case)
    await check(run.make_port())


async def test_contract_detects_naive_expires_at() -> None:
    with pytest.raises(AssertionError):
        await _run(_NaiveExpiryRun, "test_created_quote_dates_are_utc_aware")


async def test_contract_detects_expiry_that_ignores_payment_in_verification() -> None:
    with pytest.raises(AssertionError):
        await _run(_BrokenExpireRun, "test_quote_with_payment_in_verification_is_not_expired")


async def test_contract_detects_pay_advance_that_is_not_idempotent() -> None:
    with pytest.raises(AssertionError):
        await _run(_BrokenPayRun, "test_pay_advance_twice_is_idempotent")


async def test_contract_detects_a_missing_alternatives_field() -> None:
    with pytest.raises(AssertionError):
        await _run(
            _MissingAlternativesRun, "test_availability_conflict_carries_alternatives_and_handoff"
        )


async def test_unbroken_fakes_pass_the_same_cases() -> None:
    """Control: sin el defecto, los mismos casos pasan (la detección no es un falso positivo)."""

    class _OkCreate(_BrokenCreateRun):
        broken = FakeCreateQuote

    await _run(_OkCreate, "test_created_quote_dates_are_utc_aware")
    await _run(_OkCreate, "test_availability_conflict_carries_alternatives_and_handoff")
