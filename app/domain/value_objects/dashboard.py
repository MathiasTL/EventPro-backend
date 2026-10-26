"""Proyecciones inmutables y ventana mensual del dashboard ejecutivo."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.financial_reporting import (
    AccountingPeriod,
    FinancialTotals,
    PeriodType,
)
from app.domain.value_objects.money import Money


@dataclass(frozen=True)
class DashboardWindow:
    periods: tuple[AccountingPeriod, ...]

    @classmethod
    def create(cls, year: int, month: int, compare_months: int = 3) -> "DashboardWindow":
        current = AccountingPeriod.create(PeriodType.MONTHLY, year, month=month)
        if type(compare_months) is not int or not 1 <= compare_months <= 12:
            raise ValidationError("compare_months debe ser un entero entre 1 y 12.")
        index = (current.start.year - 1) * 12 + current.start.month - 1
        if index < compare_months:
            raise ValidationError("La comparación no puede retroceder antes del año 1.")
        return cls(
            tuple(
                AccountingPeriod.create(PeriodType.MONTHLY, value // 12 + 1, month=value % 12 + 1)
                for value in range(index - compare_months, index + 1)
            )
        )

    @property
    def current(self) -> AccountingPeriod:
        return self.periods[-1]


@dataclass(frozen=True)
class MonthlyTotals:
    period: str
    totals: FinancialTotals


@dataclass(frozen=True)
class PackageMetric:
    package_id: UUID
    name: str
    events: int


@dataclass(frozen=True)
class ThemeMetric:
    theme_id: UUID | None
    name: str
    events: int


@dataclass(frozen=True)
class ExtraRanking:
    extra_id: UUID
    name: str
    times_hired: int


@dataclass(frozen=True)
class DistrictTotals:
    district: str
    totals: FinancialTotals


@dataclass(frozen=True)
class DashboardReadData:
    months: tuple[MonthlyTotals, ...] = ()
    packages: tuple[PackageMetric, ...] = ()
    themes: tuple[ThemeMetric, ...] = ()
    extras: tuple[ExtraRanking, ...] = ()
    districts: tuple[DistrictTotals, ...] = ()


@dataclass(frozen=True)
class MonthlyProfit:
    period: str
    net_profit: Money


@dataclass(frozen=True)
class ProfitComparison:
    previous_period: str
    current_net_profit: Money
    previous_net_profit: Money
    absolute_change: Money
    percentage_change: Decimal | None


@dataclass(frozen=True)
class DistrictMetric:
    district: str
    events: int
    net_profit: Money


@dataclass(frozen=True)
class ExecutiveDashboard:
    period: str
    net_profit_by_month: tuple[MonthlyProfit, ...]
    net_profit_comparison: ProfitComparison
    events_by_package: tuple[PackageMetric, ...]
    events_by_theme: tuple[ThemeMetric, ...]
    top_extras: tuple[ExtraRanking, ...]
    events_by_district: tuple[DistrictMetric, ...]
