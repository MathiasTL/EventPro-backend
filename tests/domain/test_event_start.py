from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.exceptions.event_exceptions import BalancePendingError, InvalidEventStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from tests.event_support import make_event

STARTED_AT = datetime(2026, 10, 15, 21, 35, tzinfo=UTC)


@pytest.mark.parametrize("status", [EventStatus.SCHEDULED, EventStatus.AWAITING_BALANCE])
@pytest.mark.parametrize("amount", ["980.50", "1000.00"])
def test_start_from_allowed_states_with_verified_total(status: EventStatus, amount: str) -> None:
    event = make_event(status=status, pre_show_balance_paid=Money(Decimal("300")))
    verified = Money(Decimal(amount))
    event.start(verified_pre_show_amount=verified, started_at=STARTED_AT)
    assert event.status is EventStatus.IN_PROGRESS
    assert event.actual_start_time == STARTED_AT
    assert event.pre_show_balance_paid == verified
    assert event.pending_balance_to_collect == Money.zero()


@pytest.mark.parametrize("amount", ["0", "980.49"])
def test_unverified_or_partial_balance_rejects_without_mutation(amount: str) -> None:
    event = make_event(status=EventStatus.SCHEDULED, pre_show_balance_paid=Money(Decimal("980.50")))
    before = deepcopy(event)
    with pytest.raises(BalancePendingError):
        event.start(verified_pre_show_amount=Money(Decimal(amount)), started_at=STARTED_AT)
    assert event == before


@pytest.mark.parametrize(
    "status",
    [
        EventStatus.AWAITING_SIGNATURE,
        EventStatus.IN_PROGRESS,
        EventStatus.EXTENDED,
        EventStatus.SETTLED,
        EventStatus.CANCELLED,
    ],
)
def test_start_rejects_incompatible_states_without_mutation(status: EventStatus) -> None:
    event = make_event(status=status)
    before = deepcopy(event)
    with pytest.raises(InvalidEventStateError):
        event.start(verified_pre_show_amount=Money(Decimal("980.50")), started_at=STARTED_AT)
    assert event == before


def test_second_start_preserves_original_instant() -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    event.start(verified_pre_show_amount=Money(Decimal("980.50")), started_at=STARTED_AT)
    before = deepcopy(event)
    with pytest.raises(InvalidEventStateError):
        event.start(
            verified_pre_show_amount=Money(Decimal("1000")),
            started_at=STARTED_AT + timedelta(minutes=10),
        )
    assert event == before


def test_existing_instant_prevents_overwrite_even_in_scheduled_state() -> None:
    event = make_event(status=EventStatus.SCHEDULED, actual_start_time=STARTED_AT)
    before = deepcopy(event)
    with pytest.raises(InvalidEventStateError):
        event.start(verified_pre_show_amount=Money(Decimal("980.50")), started_at=STARTED_AT)
    assert event == before


def test_zero_balance_and_timezone_normalization() -> None:
    event = make_event(status=EventStatus.SCHEDULED, advance_paid=Money(Decimal("1080.50")))
    lima = STARTED_AT.astimezone(timezone(timedelta(hours=-5)))
    event.start(verified_pre_show_amount=Money.zero(), started_at=lima)
    assert event.actual_start_time == STARTED_AT
    assert event.actual_start_time.tzinfo is UTC


@pytest.mark.parametrize(
    "amount", [Money(Decimal("-0.01")), Money(Decimal("980.50"), "USD"), Money(Decimal("NaN"))]
)
def test_invalid_verified_amount_rejects_without_mutation(amount: Money) -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    before = deepcopy(event)
    with pytest.raises(ValidationError):
        event.start(verified_pre_show_amount=amount, started_at=STARTED_AT)
    assert event == before


def test_naive_start_instant_rejects_without_mutation() -> None:
    event = make_event(status=EventStatus.SCHEDULED)
    before = deepcopy(event)
    with pytest.raises(ValidationError):
        event.start(
            verified_pre_show_amount=Money(Decimal("980.50")),
            started_at=STARTED_AT.replace(tzinfo=None),
        )
    assert event == before
