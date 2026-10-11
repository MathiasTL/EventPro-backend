from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.services.financial_reporting import FinancialReportingService
from app.domain.value_objects.financial_reporting import (
    AccountingPeriod,
    EventDirectCosts,
    ExtraDirectCost,
    FinancialTotals,
    PeriodType,
)
from app.domain.value_objects.money import Money
from tests.event_support import make_event


def pen(value):
    return Money(Decimal(value))


@pytest.mark.parametrize(
    "kind,year,month,week,start,end,label",
    [
        (PeriodType.MONTHLY, 2024, 2, None, date(2024, 2, 1), date(2024, 3, 1), "2024-02"),
        (PeriodType.MONTHLY, 2026, 12, None, date(2026, 12, 1), date(2027, 1, 1), "2026-12"),
        (PeriodType.WEEKLY, 2020, None, 53, date(2020, 12, 28), date(2021, 1, 4), "2020-W53"),
        (PeriodType.WEEKLY, 2026, None, 42, date(2026, 10, 12), date(2026, 10, 19), "2026-W42"),
        (PeriodType.MONTHLY, 1, 1, None, date(1, 1, 1), date(1, 2, 1), "0001-01"),
    ],
)
def test_calendar_periods(kind, year, month, week, start, end, label):
    period = AccountingPeriod.create(kind, year, month=month, week=week)
    assert (period.start, period.end, period.label) == (start, end, label)


@pytest.mark.parametrize(
    "kind,year,month,week",
    [
        ("UNKNOWN", 2026, 10, None),
        (PeriodType.MONTHLY, True, 10, None),
        (PeriodType.MONTHLY, 0, 10, None),
        (PeriodType.MONTHLY, 9999, 10, None),
        (PeriodType.MONTHLY, 2026, None, None),
        (PeriodType.MONTHLY, 2026, 0, None),
        (PeriodType.MONTHLY, 2026, 13, None),
        (PeriodType.MONTHLY, 2026, True, None),
        (PeriodType.MONTHLY, 2026, 10, 42),
        (PeriodType.WEEKLY, 2026, 10, 42),
        (PeriodType.WEEKLY, 2026, None, None),
        (PeriodType.WEEKLY, 2021, None, 53),
        (PeriodType.WEEKLY, 2026, None, True),
        (PeriodType.WEEKLY, 2026, None, 0),
    ],
)
def test_invalid_periods(kind, year, month, week):
    with pytest.raises(ValidationError):
        AccountingPeriod.create(kind, year, month=month, week=week)


@pytest.mark.parametrize(
    "revenue,package,extras,mobility,profit,margin",
    [
        ("10000", "4000", "1000", "500", "4500.00", "45.00"),
        ("3", "1", "0", "0", "2.00", "66.67"),
        ("10", "20", "0", "0", "-10.00", "-100.00"),
        ("0", "20", "0", "0", "-20.00", "0.00"),
        ("0", "0", "0", "0", "0.00", "0.00"),
        ("200000000", "100000000", "0", "0", "100000000.00", "50.00"),
    ],
)
def test_pnl_calculation(revenue, package, extras, mobility, profit, margin):
    totals = FinancialTotals(10, pen(revenue), pen(package), pen(extras), pen(mobility))
    pnl = FinancialReportingService.consolidate(totals)
    assert pnl.net_profit == pen(profit)
    assert pnl.profit_margin_percentage == Decimal(margin)
    assert pnl.total_costs == pen(package) + pen(extras) + pen(mobility)


@pytest.mark.parametrize("amount", [pen("-1"), pen("NaN"), Money(Decimal(1), "USD"), 1])
def test_invalid_financial_amounts(amount):
    with pytest.raises(FinancialDataInconsistentError):
        FinancialTotals(1, amount, pen("0"), pen("0"), pen("0"))


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_invalid_event_count(count):
    with pytest.raises(FinancialDataInconsistentError):
        FinancialTotals(count, pen("0"), pen("0"), pen("0"), pen("0"))


def test_snapshot_counts_verified_and_legacy_extension_only_once():
    event = make_event(pre_show_balance_paid=pen("980.50"), legacy_extra_hours_amount=pen("20"))
    costs = EventDirectCosts(
        uuid4(), pen("400"), (ExtraDirectCost(uuid4(), 2, pen("50")),), pen("50")
    )
    now = datetime(2026, 10, 15, tzinfo=UTC)
    snapshot = FinancialReportingService.snapshot(event, costs, pen("80"), now)
    assert snapshot.gross_revenue == pen("1180.50")
    assert snapshot.fixed_extras_cost == pen("100")
    assert snapshot.recorded_at == now
    assert snapshot.event_id == event.id


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5])
def test_invalid_extra_quantity(quantity):
    with pytest.raises(FinancialDataInconsistentError):
        ExtraDirectCost(uuid4(), quantity, pen("50"))


def test_snapshot_requires_aware_time():
    costs = EventDirectCosts(uuid4(), pen("0"), (), pen("0"))
    with pytest.raises(FinancialDataInconsistentError):
        FinancialReportingService.snapshot(make_event(), costs, pen("0"), datetime(2026, 1, 1))
