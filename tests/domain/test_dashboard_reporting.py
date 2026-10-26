from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.services.dashboard_reporting import DashboardReportingService
from app.domain.value_objects.dashboard import (
    DashboardReadData,
    DashboardWindow,
    DistrictTotals,
    ExtraRanking,
    MonthlyTotals,
    PackageMetric,
    ThemeMetric,
)
from tests.dashboard_support import totals


@pytest.mark.parametrize(
    "year,month,count,start,end",
    [
        (2026, 1, 3, date(2025, 10, 1), date(2026, 2, 1)),
        (2024, 2, 1, date(2024, 1, 1), date(2024, 3, 1)),
        (9998, 12, 12, date(9997, 12, 1), date(9999, 1, 1)),
        (1, 2, 1, date(1, 1, 1), date(1, 3, 1)),
    ],
)
def test_window(year, month, count, start, end):
    window = DashboardWindow.create(year, month, count)
    assert window.periods[0].start == start
    assert window.current.end == end
    assert len(window.periods) == count + 1
    with pytest.raises(FrozenInstanceError):
        window.periods = ()


@pytest.mark.parametrize(
    "year,month,count",
    [
        (0, 1, 1),
        (9999, 1, 1),
        (2026, 0, 1),
        (2026, 13, 1),
        (2026, True, 1),
        (True, 1, 1),
        (2026, 10, 0),
        (2026, 10, 13),
        (2026, 10, True),
        (2026, 10, 1.5),
        (1, 1, 1),
        (1, 3, 3),
    ],
)
def test_invalid_window(year, month, count):
    with pytest.raises(ValidationError):
        DashboardWindow.create(year, month, count)


@pytest.mark.parametrize(
    "previous,current,percentage",
    [
        ("0", "0", "0.00"),
        ("0", "100", None),
        ("0", "-100", None),
        ("100", "0", "-100.00"),
        ("100", "150", "50.00"),
        ("-100", "-50", "50.00"),
        ("-100", "100", "200.00"),
        ("-100", "-150", "-50.00"),
        ("3", "4", "33.33"),
        ("32", "33", "3.13"),
    ],
)
def test_profit_comparison(previous, current, percentage):
    data = DashboardReadData(
        months=(
            MonthlyTotals("2026-09", totals(previous)),
            MonthlyTotals("2026-10", totals(current)),
        )
    )
    result = DashboardReportingService.build(DashboardWindow.create(2026, 10), data)
    comparison = result.net_profit_comparison
    assert comparison.previous_period == "2026-09"
    assert comparison.absolute_change.amount == Decimal(current) - Decimal(previous)
    assert comparison.percentage_change == (None if percentage is None else Decimal(percentage))
    assert [row.period for row in result.net_profit_by_month] == [
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    ]
    assert result.net_profit_by_month[0].net_profit.amount == 0


def test_empty_current_month_preserves_history():
    data = DashboardReadData(months=(MonthlyTotals("2026-09", totals("25")),))
    result = DashboardReportingService.build(DashboardWindow.create(2026, 10), data)
    assert result.net_profit_comparison.percentage_change == Decimal("-100.00")
    assert result.events_by_package == result.events_by_theme == result.top_extras == ()
    assert result.events_by_district == ()


def test_rankings_are_deterministic_and_immutable():
    first, second = UUID(int=1), UUID(int=2)
    data = DashboardReadData(
        packages=(PackageMetric(second, "A", 2), PackageMetric(first, "A", 2)),
        themes=(ThemeMetric(None, "Sin temática", 1), ThemeMetric(first, "Selva", 2)),
        extras=(ExtraRanking(second, "B", 3), ExtraRanking(first, "A", 3)),
        districts=(DistrictTotals("A", totals("-2")), DistrictTotals("B", totals("50"))),
    )
    result = DashboardReportingService.build(DashboardWindow.create(2026, 10), data)
    assert result.events_by_package[0].package_id == first
    assert result.events_by_theme[0].theme_id == first
    assert result.top_extras[0].extra_id == first
    assert result.events_by_district[0].district == "B"
    with pytest.raises(FrozenInstanceError):
        result.top_extras[0].times_hired = 5
