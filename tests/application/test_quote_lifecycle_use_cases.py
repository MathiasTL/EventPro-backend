"""Casos de uso reales de pago del adelanto y cancelación (E1, US-07 y RN-09)."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dtos.availability_dto import AvailabilityResult, AvailabilityStatus
from app.application.dtos.quote_dto import (
    BankTransferInstructionDTO,
    PaymentInstructionsDTO,
    WalletInstructionDTO,
)
from app.application.use_cases.quote.cancel_quote import CancelQuoteUseCase
from app.application.use_cases.quote.pay_advance import PayAdvanceUseCase
from app.domain.entities.quote import Quote, QuoteStatus
from app.domain.exceptions.quote_exceptions import (
    AvailabilityConflictError,
    InvalidQuoteStateError,
    QuoteExpiredError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from tests.domain.quote_support import NOW, make_quote

PACKAGE_ID = uuid4()
INSTRUCTIONS = PaymentInstructionsDTO(
    yape=WalletInstructionDTO(phone="900000000", holder="Titular"),
    plin=WalletInstructionDTO(phone="900000000", holder="Titular"),
    bank_transfer=BankTransferInstructionDTO(
        bank="Banco", account="000-00000000-0-00", cci="00000000000000000000", holder="Titular"
    ),
)


def _quote() -> Quote:
    return make_quote(now=NOW, package_id=PACKAGE_ID)


def _quotes(quote: Quote | None, *, payment_in_review: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        get_by_id_for_update=AsyncMock(return_value=quote),
        save=AsyncMock(side_effect=lambda saved: saved),
        has_payment_in_review=AsyncMock(return_value=payment_in_review),
    )


def _catalog() -> SimpleNamespace:
    return SimpleNamespace(
        get_package=AsyncMock(return_value=SimpleNamespace(duration_minutes=90, is_active=True))
    )


def _availability(result: AvailabilityResult | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        check_availability=AsyncMock(
            return_value=result or AvailabilityResult(AvailabilityStatus.AVAILABLE)
        )
    )


def _port(
    quote: Quote | None,
    *,
    now: object = NOW,
    availability: SimpleNamespace | None = None,
) -> tuple[PayAdvanceUseCase, SimpleNamespace, SimpleNamespace]:
    quotes = _quotes(quote)
    catalog = _catalog()
    availability = availability or _availability()
    port = PayAdvanceUseCase(
        quotes,
        catalog,
        availability,
        SimpleNamespace(utcnow=lambda: now),
        INSTRUCTIONS,
        recheck_minutes=60,
    )
    return port, quotes, availability


async def test_pay_advance_fresh_does_not_recheck_and_starts_payment() -> None:
    quote = _quote()
    port, quotes, availability = _port(quote)

    result = await port.execute(quote.id)

    assert result.status is QuoteStatus.PAYMENT_STARTED
    assert result.rechecked is False
    assert result.advance_amount == quote.liquidation.advance_amount.amount
    assert result.payment_instructions is INSTRUCTIONS
    assert quote.status is QuoteStatus.PAYMENT_STARTED
    availability.check_availability.assert_not_awaited()
    quotes.save.assert_awaited_once_with(quote)


async def test_pay_advance_rechecks_after_the_window_with_the_package_duration() -> None:
    quote = _quote()
    port, _, availability = _port(quote, now=NOW + timedelta(minutes=61))

    result = await port.execute(quote.id)

    assert result.rechecked is True
    request = availability.check_availability.await_args.args[0]
    assert (request.event_date, request.start_time) == (quote.event_date, quote.event_time)
    assert (request.duration_minutes, request.package_id) == (90, PACKAGE_ID)


async def test_pay_advance_conflict_keeps_state_and_offers_alternatives() -> None:
    quote = _quote()

    async def check(request):
        status = (
            AvailabilityStatus.CONFLICT
            if request.event_date == quote.event_date
            else AvailabilityStatus.AVAILABLE
        )
        return AvailabilityResult(status)

    availability = SimpleNamespace(check_availability=AsyncMock(side_effect=check))
    port, quotes, _ = _port(quote, now=NOW + timedelta(minutes=61), availability=availability)

    with pytest.raises(AvailabilityConflictError) as caught:
        await port.execute(quote.id)

    assert len(caught.value.alternatives) == 3
    assert caught.value.handoff_available is True
    assert quote.status is QuoteStatus.SENT
    quotes.save.assert_not_awaited()


async def test_pay_advance_manual_approval_is_a_threshold_error() -> None:
    quote = _quote()
    availability = _availability(AvailabilityResult(AvailabilityStatus.REQUIRES_MANUAL_APPROVAL))
    port, quotes, _ = _port(quote, now=NOW + timedelta(minutes=61), availability=availability)

    with pytest.raises(SimultaneousThresholdExceededError):
        await port.execute(quote.id)

    assert quote.status is QuoteStatus.SENT
    quotes.save.assert_not_awaited()


async def test_pay_advance_expired_by_deadline_does_not_recheck() -> None:
    quote = _quote()
    port, _, availability = _port(quote, now=quote.expires_at)

    with pytest.raises(QuoteExpiredError):
        await port.execute(quote.id)

    availability.check_availability.assert_not_awaited()


async def test_pay_advance_expired_status_raises() -> None:
    quote = _quote()
    quote.status = QuoteStatus.EXPIRED
    port, quotes, _ = _port(quote)

    with pytest.raises(QuoteExpiredError):
        await port.execute(quote.id)

    quotes.save.assert_not_awaited()


@pytest.mark.parametrize("status", [QuoteStatus.CONVERTED, QuoteStatus.CANCELLED])
async def test_pay_advance_terminal_states_are_invalid(status: QuoteStatus) -> None:
    quote = _quote()
    quote.status = status
    port, _, _ = _port(quote)

    with pytest.raises(InvalidQuoteStateError):
        await port.execute(quote.id)


async def test_pay_advance_is_idempotent_from_payment_started() -> None:
    quote = _quote()
    quote.status = QuoteStatus.PAYMENT_STARTED
    port, quotes, availability = _port(quote, now=NOW + timedelta(hours=2))

    result = await port.execute(quote.id)

    assert result.status is QuoteStatus.PAYMENT_STARTED
    assert result.rechecked is False
    assert result.payment_deadline == quote.expires_at
    quotes.save.assert_not_awaited()
    availability.check_availability.assert_not_awaited()


async def test_pay_advance_unknown_quote_raises_not_found() -> None:
    port, _, _ = _port(None)

    with pytest.raises(QuoteNotFoundError):
        await port.execute(uuid4())


async def test_cancel_quote_from_sent_stores_reason_and_saves() -> None:
    quote = _quote()
    quotes = _quotes(quote)

    result = await CancelQuoteUseCase(quotes).execute(quote.id, "El cliente cambió")

    assert result.status is QuoteStatus.CANCELLED
    assert quote.status is QuoteStatus.CANCELLED
    assert quote.cancellation_reason == "El cliente cambió"
    quotes.save.assert_awaited_once_with(quote)


async def test_cancel_quote_from_payment_started_is_allowed() -> None:
    quote = _quote()
    quote.status = QuoteStatus.PAYMENT_STARTED
    quotes = _quotes(quote)

    result = await CancelQuoteUseCase(quotes).execute(quote.id)

    assert result.status is QuoteStatus.CANCELLED
    assert quote.cancellation_reason is None


async def test_cancel_quote_rejects_a_payment_in_review() -> None:
    quote = _quote()
    quote.status = QuoteStatus.PAYMENT_STARTED
    quotes = _quotes(quote, payment_in_review=True)

    with pytest.raises(InvalidQuoteStateError):
        await CancelQuoteUseCase(quotes).execute(quote.id)

    assert quote.status is QuoteStatus.PAYMENT_STARTED
    quotes.save.assert_not_awaited()


async def test_cancel_quote_is_not_idempotent() -> None:
    quote = _quote()
    quotes = _quotes(quote)
    port = CancelQuoteUseCase(quotes)
    await port.execute(quote.id)

    with pytest.raises(InvalidQuoteStateError):
        await port.execute(quote.id)

    quotes.save.assert_awaited_once_with(quote)


async def test_cancel_quote_unknown_quote_raises_not_found() -> None:
    with pytest.raises(QuoteNotFoundError):
        await CancelQuoteUseCase(_quotes(None)).execute(uuid4())
