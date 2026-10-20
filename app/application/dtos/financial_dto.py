from dataclasses import dataclass
from decimal import Decimal

from app.domain.value_objects.financial_reporting import PeriodType


@dataclass(frozen=True)
class FinancialPnlRequest:
    period_type: PeriodType
    year: int
    month: int | None = None
    week: int | None = None


@dataclass(frozen=True)
class FinancialDirectCostsDTO:
    fixed_packages_cost: Decimal
    fixed_extras_cost: Decimal
    mobility_operational_cost: Decimal
    total_costs: Decimal


@dataclass(frozen=True)
class FinancialPnlDTO:
    period: str
    total_events_settled: int
    gross_revenue: Decimal
    direct_costs: FinancialDirectCostsDTO
    net_profit: Decimal
    profit_margin_percentage: Decimal
