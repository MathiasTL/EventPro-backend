from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.exceptions.event_exceptions import (
    BalancePendingError,
    ExtensionPaymentMismatchError,
    InvalidEventStateError,
)
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from tests.event_support import make_event

NOW = datetime(2026, 10, 16, tzinfo=UTC)


def extend(event, minutes=30, amount="100", at=NOW):
    return event.extend(
        extra_minutes=minutes,
        agreed_rate=Money(Decimal(amount)),
        payment_id=uuid4(),
        requested_at=at,
    )


@pytest.mark.parametrize("status", [EventStatus.IN_PROGRESS, EventStatus.EXTENDED])
def test_extensions_accumulate_exactly_and_preserve_contracted_data(status):
    event = make_event(status=status, pre_show_balance_paid=Money(Decimal("980.50")))
    original = deepcopy(event)
    extension = extend(event)
    extend(event, 60, "125.25")
    assert extension.event_id == event.id
    assert extension.extra_minutes == 30
    assert extension.agreed_rate == Money(Decimal("100"))
    assert extension.requested_at == NOW
    assert event.status is EventStatus.EXTENDED
    assert event.extra_minutes_total == 90
    assert event.extra_hours_amount == Money(Decimal("225.25"))
    assert event.final_total_amount == Money(Decimal("1305.75"))
    assert event.pending_balance_to_collect == Money.zero()
    assert event.extended_time_window.end == original.time_window.end + timedelta(minutes=90)
    for field in (
        "end_time",
        "start_time",
        "event_date",
        "actual_start_time",
        "advance_paid",
        "pre_show_balance_paid",
        "total_services_amount",
        "total_mobility_amount",
    ):
        assert getattr(event, field) == getattr(original, field)


def test_extended_window_crosses_midnight_and_multiple_days():
    event = make_event(status=EventStatus.IN_PROGRESS, start_time=time(23), end_time=time(0))
    original_end = event.time_window.end
    extend(event, 1500)
    assert event.extended_time_window.end == original_end + timedelta(minutes=1500)
    assert event.end_time == time(0)


@pytest.mark.parametrize("minutes", [0, -1, 1.5, True, 2147483648])
def test_invalid_minutes_leave_event_unchanged(minutes):
    event = make_event(status=EventStatus.IN_PROGRESS)
    original = deepcopy(event)
    with pytest.raises(ValidationError):
        extend(event, minutes)
    assert event == original


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "99999999.99"])
def test_invalid_or_overflowing_charge_leaves_event_unchanged(amount):
    event = make_event(status=EventStatus.IN_PROGRESS)
    original = deepcopy(event)
    with pytest.raises(ValidationError):
        extend(event, amount=amount)
    assert event == original


def test_wrong_currency_and_naive_timestamp_are_rejected():
    event = make_event(status=EventStatus.IN_PROGRESS)
    original = deepcopy(event)
    with pytest.raises(ValidationError):
        event.extend(
            extra_minutes=30,
            agreed_rate=Money(Decimal("10"), "USD"),
            payment_id=uuid4(),
            requested_at=NOW,
        )
    with pytest.raises(ValidationError):
        extend(event, at=NOW.replace(tzinfo=None))
    assert event == original


@pytest.mark.parametrize(
    "status", [s for s in EventStatus if s not in (EventStatus.IN_PROGRESS, EventStatus.EXTENDED)]
)
def test_extension_and_settlement_reject_incompatible_states(status):
    event = make_event(status=status)
    original = deepcopy(event)
    with pytest.raises(InvalidEventStateError):
        extend(event)
    with pytest.raises(InvalidEventStateError):
        event.settle(verified_extension_amount=Money.zero(), verified_extra_minutes=0)
    assert event == original


@pytest.mark.parametrize("with_extension", [False, True])
def test_settlement_changes_only_state_and_cannot_be_repeated(with_extension):
    event = make_event(
        status=EventStatus.IN_PROGRESS, pre_show_balance_paid=Money(Decimal("980.50"))
    )
    if with_extension:
        extend(event)
    original = deepcopy(event)
    event.settle(
        verified_extension_amount=event.extra_hours_amount,
        verified_extra_minutes=event.extra_minutes_total,
    )
    assert event.status is EventStatus.SETTLED
    original.status = EventStatus.SETTLED
    assert event == original
    with pytest.raises(InvalidEventStateError):
        extend(event)
    with pytest.raises(InvalidEventStateError):
        event.settle(
            verified_extension_amount=event.extra_hours_amount,
            verified_extra_minutes=event.extra_minutes_total,
        )


def test_settlement_requires_complete_coverage_and_matching_extensions():
    event = make_event(status=EventStatus.IN_PROGRESS)
    original = deepcopy(event)
    with pytest.raises(BalancePendingError):
        event.settle(verified_extension_amount=Money.zero(), verified_extra_minutes=0)
    assert event == original
    extend(event)
    original = deepcopy(event)
    for amount, minutes in (("0", 30), ("100", 0), ("101", 30)):
        with pytest.raises(ExtensionPaymentMismatchError):
            event.settle(
                verified_extension_amount=Money(Decimal(amount)), verified_extra_minutes=minutes
            )
        assert event == original


def test_extension_normalizes_server_timestamp_to_utc():
    event = make_event(status=EventStatus.IN_PROGRESS)
    at = datetime(2026, 10, 15, 19, tzinfo=timezone(timedelta(hours=-5)))
    assert extend(event, at=at).requested_at == NOW


def test_minute_and_calendar_overflow_leave_event_unchanged():
    for event in (
        make_event(status=EventStatus.IN_PROGRESS, extra_minutes_total=2147483647),
        make_event(status=EventStatus.IN_PROGRESS, event_date=date(9999, 12, 31)),
    ):
        original = deepcopy(event)
        with pytest.raises(ValidationError):
            extend(event, minutes=120)
        assert event == original
