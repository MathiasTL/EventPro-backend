from dataclasses import dataclass
from decimal import Decimal

from app.domain.value_objects.dashboard import ExtraRanking, PackageMetric, ThemeMetric


@dataclass(frozen=True)
class ExecutiveDashboardRequest:
    year: int
    month: int
    compare_months: int = 3


@dataclass(frozen=True)
class MonthlyProfitDTO:
    period: str
    net_profit: Decimal


@dataclass(frozen=True)
class ProfitComparisonDTO:
    previous_period: str
    current_net_profit: Decimal
    previous_net_profit: Decimal
    absolute_change: Decimal
    percentage_change: Decimal | None


@dataclass(frozen=True)
class DistrictMetricDTO:
    district: str
    events: int
    net_profit: Decimal


@dataclass(frozen=True)
class ExecutiveDashboardDTO:
    period: str
    net_profit_by_month: tuple[MonthlyProfitDTO, ...]
    net_profit_comparison: ProfitComparisonDTO
    events_by_package: tuple[PackageMetric, ...]
    events_by_theme: tuple[ThemeMetric, ...]
    top_extras: tuple[ExtraRanking, ...]
    events_by_district: tuple[DistrictMetricDTO, ...]
