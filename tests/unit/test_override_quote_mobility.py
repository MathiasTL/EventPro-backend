"""Pruebas unitarias de OverrideQuoteMobilityUseCase (RF-21, US-19)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dtos.override_dto import OverrideMobilityInput
from app.application.services.audit_service import AuditService
from app.application.use_cases.quote.override_mobility import OverrideQuoteMobilityUseCase
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from tests.domain.financial_support import default_engine, pen
from tests.domain.quote_support import make_quote

USER_ID = uuid4()


def _use_case(quote) -> tuple[OverrideQuoteMobilityUseCase, AsyncMock, AsyncMock]:
    quotes = AsyncMock()
    quotes.get_by_id.return_value = quote
    audit_port = AsyncMock()
    use_case = OverrideQuoteMobilityUseCase(quotes, default_engine(), AuditService(audit_port))
    return use_case, quotes, audit_port


def _input(quote_id, *, amount: str = "95.00", reason: str = "Peajes no computados"):
    return OverrideMobilityInput(
        quote_id=quote_id,
        manual_mobility_amount=Decimal(amount),
        reason=reason,
        decided_by_user_id=USER_ID,
    )


def test_override_recalculates_total_and_balance_keeping_advance() -> None:
    quote = make_quote()
    original_advance = quote.liquidation.advance_amount
    use_case, quotes, audit_port = _use_case(quote)

    result = asyncio.run(use_case.execute(_input(quote.id)))

    assert result.mobility_amount == pen("95.00").amount
    assert result.advance_amount == original_advance.amount
    assert result.pending_balance == result.total_amount - result.advance_amount
    assert result.mobility_overridden is True
    assert quote.mobility_overridden is True
    assert quote.mobility_override_reason == "Peajes no computados"
    quotes.save.assert_awaited_once_with(quote)
    entry = audit_port.record.await_args.args[0]
    assert entry.action == "OVERRIDE_MOBILITY"
    assert entry.entity_id == quote.id
    assert entry.user_id == USER_ID
    assert entry.old_values["mobility_overridden"] is False


def test_missing_quote_raises() -> None:
    use_case, quotes, audit_port = _use_case(None)
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(use_case.execute(_input(uuid4())))
    quotes.save.assert_not_awaited()
    audit_port.record.assert_not_awaited()


@pytest.mark.parametrize("status", [QuoteStatus.CONVERTED, QuoteStatus.CANCELLED])
def test_converted_or_cancelled_quote_raises_invalid_state(status: QuoteStatus) -> None:
    quote = make_quote()
    quote.status = status
    use_case, quotes, audit_port = _use_case(quote)

    with pytest.raises(InvalidQuoteStateError):
        asyncio.run(use_case.execute(_input(quote.id)))
    quotes.save.assert_not_awaited()
    audit_port.record.assert_not_awaited()


def test_negative_amount_raises_validation_error() -> None:
    quote = make_quote()
    use_case, quotes, _audit_port = _use_case(quote)

    with pytest.raises(ValidationError):
        asyncio.run(use_case.execute(_input(quote.id, amount="-5.00")))
    quotes.save.assert_not_awaited()


def test_blank_reason_raises_validation_error() -> None:
    quote = make_quote()
    use_case, quotes, _audit_port = _use_case(quote)

    with pytest.raises(ValidationError):
        asyncio.run(use_case.execute(_input(quote.id, reason="   ")))
    quotes.save.assert_not_awaited()
