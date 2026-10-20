from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities.quote import Quote, QuoteExtraLine, QuoteSource, QuoteStatus
from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError, QuoteExpiredError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.mobility import MobilityZone, RouteEstimate

from .financial_support import default_engine, pen
from .quote_support import NOW, make_quote


def test_create_starts_sent_and_freezes_liquidation() -> None:
    quote = make_quote()
    assert quote.status is QuoteStatus.SENT
    assert quote.sent_at == NOW
    assert quote.expires_at == NOW + timedelta(hours=24)
    assert quote.liquidation.services_subtotal == pen("1150.75")
    assert quote.liquidation.mobility_amount == pen("45.00")  # contingencia zona 2
    assert quote.base_mobility_amount == pen("45.00")
    assert quote.calculated_distance_km is None
    assert quote.calculated_transit_minutes is None
    assert not quote.is_terminal


def test_create_copies_route_estimate_fields() -> None:
    quote = make_quote(estimate=RouteEstimate(Decimal("20.00"), 30))
    assert quote.calculated_distance_km == Decimal("20.00")
    assert quote.calculated_transit_minutes == 30
    assert quote.base_mobility_amount == pen("29.00")
    assert quote.liquidation.mobility_amount == pen("33.35")


def test_create_honors_custom_deadline() -> None:
    assert make_quote(deadline_hours=2).expires_at == NOW + timedelta(hours=2)


def test_create_normalizes_aware_datetimes_to_utc() -> None:
    lima = timezone(timedelta(hours=-5))
    quote = make_quote(now=datetime(2026, 10, 7, 10, 0, tzinfo=lima))
    assert quote.sent_at == NOW
    assert quote.sent_at.utcoffset() == timedelta(0)
    assert quote.expires_at.utcoffset() == timedelta(0)


def test_create_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        make_quote(now=datetime(2026, 10, 7, 15, 0))


@pytest.mark.parametrize("hours", [0, -1, True, 1.5])
def test_create_rejects_invalid_deadline(hours: object) -> None:
    with pytest.raises(ValidationError):
        make_quote(deadline_hours=hours)


def test_create_rejects_liquidation_that_does_not_match_mobility() -> None:
    engine = default_engine()
    other = engine.liquidate(package_price=pen("1000.00"), extras=[], mobility_amount=pen("1.00"))
    with pytest.raises(ValidationError):
        make_quote(liquidation=other)


def test_create_rejects_exemption_flag_with_route_result() -> None:
    engine = default_engine()
    route = engine.resolve_mobility(
        client_provides_mobility=False,
        estimate=RouteEstimate(Decimal("20.00"), 30),
        zone=MobilityZone.ZONE_2,
    )
    liquidation = engine.liquidate(
        package_price=pen("1000.00"), extras=[], mobility_amount=route.final_amount
    )
    with pytest.raises(ValidationError):
        make_quote(
            client_provides_mobility=True, mobility=route, liquidation=liquidation, extras=[]
        )


def test_create_rejects_exempt_result_without_exemption_flag() -> None:
    engine = default_engine()
    exempt = engine.resolve_mobility(
        client_provides_mobility=True, estimate=None, zone=MobilityZone.ZONE_2
    )
    liquidation = engine.liquidate(
        package_price=pen("1000.00"), extras=[], mobility_amount=exempt.final_amount
    )
    with pytest.raises(ValidationError):
        make_quote(
            client_provides_mobility=False, mobility=exempt, liquidation=liquidation, extras=[]
        )


def test_create_accepts_consistent_exemption() -> None:
    assert make_quote(client_provides_mobility=True).client_provides_mobility is True


def test_create_rejects_extras_above_services_subtotal() -> None:
    line = QuoteExtraLine(uuid4(), 1, pen("5000.00"), pen("5000.00"))
    with pytest.raises(ValidationError):
        make_quote(extras=[line])


def test_create_rejects_blank_location() -> None:
    with pytest.raises(ValidationError):
        make_quote(location_district="   ")


def test_manual_quote_starts_payment_immediately() -> None:
    quote = make_quote(source=QuoteSource.MANUAL, manual_request_hash="a" * 64)
    quote.start_payment(NOW)
    assert quote.source is QuoteSource.MANUAL
    assert quote.status is QuoteStatus.PAYMENT_STARTED
    assert quote.manual_request_hash == "a" * 64


def test_start_payment_moves_sent_to_payment_started() -> None:
    quote = make_quote()
    quote.start_payment(NOW + timedelta(hours=1))
    assert quote.status is QuoteStatus.PAYMENT_STARTED


def test_start_payment_is_idempotent() -> None:
    quote = make_quote()
    quote.start_payment(NOW)
    quote.start_payment(NOW + timedelta(minutes=5))
    assert quote.status is QuoteStatus.PAYMENT_STARTED


def test_start_payment_when_already_started_is_a_noop_even_after_expiry() -> None:
    # La idempotencia prevalece: el vencimiento de un pago ya iniciado lo decide expire().
    quote = make_quote()
    quote.start_payment(NOW)
    quote.start_payment(quote.expires_at + timedelta(hours=1))
    assert quote.status is QuoteStatus.PAYMENT_STARTED


def test_start_payment_one_microsecond_before_expiry_is_allowed() -> None:
    quote = make_quote()
    quote.start_payment(quote.expires_at - timedelta(microseconds=1))
    assert quote.status is QuoteStatus.PAYMENT_STARTED


def test_start_payment_at_exact_expiry_raises_quote_expired() -> None:
    quote = make_quote()
    with pytest.raises(QuoteExpiredError):
        quote.start_payment(quote.expires_at)
    assert quote.status is QuoteStatus.SENT


def test_start_payment_after_expiry_raises_quote_expired() -> None:
    quote = make_quote()
    with pytest.raises(QuoteExpiredError):
        quote.start_payment(quote.expires_at + timedelta(seconds=1))


def test_start_payment_from_expired_raises_quote_expired() -> None:
    quote = make_quote()
    quote.expire(quote.expires_at)
    with pytest.raises(QuoteExpiredError):
        quote.start_payment(NOW)


@pytest.mark.parametrize("terminal", [QuoteStatus.CONVERTED, QuoteStatus.CANCELLED])
def test_start_payment_from_converted_or_cancelled_is_invalid(terminal: QuoteStatus) -> None:
    quote = make_quote()
    quote.status = terminal
    with pytest.raises(InvalidQuoteStateError):
        quote.start_payment(NOW)


def test_start_payment_rejects_naive_datetime() -> None:
    quote = make_quote()
    with pytest.raises(ValidationError):
        quote.start_payment(datetime(2026, 10, 7, 15, 0))
    assert quote.status is QuoteStatus.SENT


def test_convert_only_from_payment_started() -> None:
    quote = make_quote()
    with pytest.raises(InvalidQuoteStateError):
        quote.convert()
    quote.start_payment(NOW)
    quote.convert()
    assert quote.status is QuoteStatus.CONVERTED
    assert quote.is_terminal


@pytest.mark.parametrize(
    "status", [QuoteStatus.EXPIRED, QuoteStatus.CANCELLED, QuoteStatus.CONVERTED]
)
def test_convert_rejects_terminal_states(status: QuoteStatus) -> None:
    quote = make_quote()
    quote.status = status
    with pytest.raises(InvalidQuoteStateError):
        quote.convert()


@pytest.mark.parametrize("started", [False, True])
def test_expire_from_open_states_at_the_exact_boundary(started: bool) -> None:
    quote = make_quote()
    if started:
        quote.start_payment(NOW)
    quote.expire(quote.expires_at)
    assert quote.status is QuoteStatus.EXPIRED
    assert quote.is_terminal


def test_expire_before_expiry_is_invalid() -> None:
    quote = make_quote()
    with pytest.raises(InvalidQuoteStateError):
        quote.expire(quote.expires_at - timedelta(microseconds=1))
    assert quote.status is QuoteStatus.SENT


@pytest.mark.parametrize(
    "status", [QuoteStatus.EXPIRED, QuoteStatus.CANCELLED, QuoteStatus.CONVERTED]
)
def test_expire_rejects_terminal_states(status: QuoteStatus) -> None:
    quote = make_quote()
    quote.status = status
    with pytest.raises(InvalidQuoteStateError):
        quote.expire(quote.expires_at + timedelta(hours=1))


def test_expire_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        make_quote().expire(datetime(2026, 10, 9, 15, 0))


@pytest.mark.parametrize("started", [False, True])
def test_cancel_from_open_states(started: bool) -> None:
    quote = make_quote()
    if started:
        quote.start_payment(NOW)
    quote.cancel("  El cliente desistió  ")
    assert quote.status is QuoteStatus.CANCELLED
    assert quote.cancellation_reason == "El cliente desistió"
    assert quote.is_terminal


def test_cancel_reason_is_optional() -> None:
    quote = make_quote()
    quote.cancel()
    assert quote.cancellation_reason is None
    other = make_quote()
    other.cancel("   ")
    assert other.cancellation_reason is None


@pytest.mark.parametrize(
    "status", [QuoteStatus.EXPIRED, QuoteStatus.CANCELLED, QuoteStatus.CONVERTED]
)
def test_cancel_rejects_terminal_states(status: QuoteStatus) -> None:
    quote = make_quote()
    quote.status = status
    with pytest.raises(InvalidQuoteStateError):
        quote.cancel("tarde")


def test_extra_line_validations() -> None:
    extra_id = uuid4()
    assert QuoteExtraLine(extra_id, 2, pen("10.00"), pen("20.00")).subtotal == pen("20.00")
    with pytest.raises(ValidationError):
        QuoteExtraLine(extra_id, 0, pen("10.00"), pen("0.00"))
    with pytest.raises(ValidationError):
        QuoteExtraLine(extra_id, True, pen("10.00"), pen("10.00"))
    with pytest.raises(ValidationError):
        QuoteExtraLine(extra_id, 1, pen("-1.00"), pen("-1.00"))
    with pytest.raises(ValidationError):
        QuoteExtraLine(extra_id, 2, pen("10.00"), pen("19.99"))


def test_zero_price_extra_line_is_valid() -> None:
    line = QuoteExtraLine(uuid4(), 5, pen("0.00"), pen("0.00"))
    quote = make_quote(extras=[line])
    assert quote.extras == (line,)


def test_quote_keeps_defaults_for_unused_optional_fields() -> None:
    quote = make_quote()
    assert quote.theme_id is None
    assert quote.latitude is None
    assert quote.mobility_overridden is False
    assert isinstance(quote, Quote)
