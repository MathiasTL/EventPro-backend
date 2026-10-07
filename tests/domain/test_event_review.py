from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.exceptions.event_exceptions import ExtensionPaymentMismatchError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from tests.domain.test_event_extensions import extend
from tests.event_support import make_event


def test_operational_window_is_consumed_without_losing_contracted_end():
    event = make_event(status=EventStatus.IN_PROGRESS)
    scheduled = event.scheduled_time_window
    extend(event, 150)
    assert event.time_window.end == scheduled.end + timedelta(minutes=150)
    assert event.extended_time_window == event.time_window
    assert event.time_window.end.date() == date(2026, 10, 16)
    assert event.scheduled_time_window == scheduled


def test_historical_credit_allows_closing_but_does_not_hide_missing_new_extensions():
    event = make_event(
        status=EventStatus.IN_PROGRESS,
        pre_show_balance_paid=Money(Decimal("980.50")),
        final_total_amount=Money(Decimal("1160.50")),
        extra_hours_amount=Money(Decimal("80")),
        legacy_extra_hours_amount=Money(Decimal("80")),
    )
    event.settle(verified_extension_amount=Money.zero(), verified_extra_minutes=0)
    assert event.status is EventStatus.SETTLED
    event.status = EventStatus.IN_PROGRESS
    extend(event, 30, "100")
    original = deepcopy(event)
    with pytest.raises(ExtensionPaymentMismatchError):
        event.settle(verified_extension_amount=Money.zero(), verified_extra_minutes=0)
    assert event == original
