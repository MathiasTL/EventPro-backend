from datetime import UTC, date, time
from decimal import Decimal

import pytest

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from tests.event_support import make_event


def test_event_defaults_and_literal_observations() -> None:
    text = "  MÚSICA PROHIBIDA: Reggaetón.\nGorila al min 45.  "
    event = make_event(client_observations=text)
    assert event.status is EventStatus.AWAITING_SIGNATURE
    assert event.client_observations == text
    assert event.pre_show_balance_paid == Money.zero()
    assert event.extra_hours_amount == Money.zero()
    assert event.created_at.tzinfo == UTC
    assert make_event().client_observations is None


def test_event_status_codes_match_documented_lifecycle() -> None:
    assert {state.value for state in EventStatus} == {
        "AWAITING_SIGNATURE",
        "SCHEDULED",
        "AWAITING_BALANCE",
        "IN_PROGRESS",
        "EXTENDED",
        "SETTLED",
        "CANCELLED",
    }
    for status in EventStatus:
        assert make_event(status=status).status is status


@pytest.mark.parametrize("field,limit", [("event_code", 30), ("address", 255), ("district", 80)])
@pytest.mark.parametrize("invalid", ["", "   ", "too_long"])
def test_event_rejects_invalid_required_text(field: str, limit: int, invalid: str) -> None:
    value = "x" * (limit + 1) if invalid == "too_long" else invalid
    with pytest.raises(ValidationError):
        make_event(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "total_services_amount",
        "total_mobility_amount",
        "final_total_amount",
        "advance_paid",
        "pre_show_balance_paid",
        "extra_hours_amount",
    ],
)
def test_event_rejects_negative_amounts(field: str) -> None:
    with pytest.raises(ValidationError):
        make_event(**{field: Money(Decimal("-0.01"))})


def test_event_requires_pen_and_a_real_status() -> None:
    with pytest.raises(ValidationError):
        make_event(advance_paid=Money(Decimal("10"), "USD"))
    with pytest.raises(ValidationError):
        make_event(status="UNKNOWN")


def test_event_rejects_empty_window_and_supports_midnight() -> None:
    with pytest.raises(ValidationError):
        make_event(start_time=time(22), end_time=time(22))
    event = make_event(start_time=time(23, 30), end_time=time(0, 30))
    assert event.time_window.start.date() == date(2026, 10, 15)
    assert event.time_window.end.date() == date(2026, 10, 16)
    assert event.time_window.duration_minutes == 60


@pytest.mark.parametrize(
    "paid,expected", [("0", "980.50"), ("900", "80.50"), ("980.50", "0"), ("1100", "0")]
)
def test_pending_balance_is_exact_and_never_negative(paid: str, expected: str) -> None:
    event = make_event(
        pre_show_balance_paid=Money(Decimal(paid)), extra_hours_amount=Money(Decimal("80"))
    )
    assert event.pending_balance_to_collect == Money(Decimal(expected))
