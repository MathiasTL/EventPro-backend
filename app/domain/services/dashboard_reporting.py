"""Composición pura de indicadores a partir de agregados financieros."""

from decimal import ROUND_HALF_UP, Decimal

from app.domain.services.financial_reporting import FinancialReportingService
from app.domain.value_objects.dashboard import (
    DashboardReadData,
    DashboardWindow,
    DistrictMetric,
    ExecutiveDashboard,
    MonthlyProfit,
    ProfitComparison,
)
from app.domain.value_objects.money import Money


class DashboardReportingService:
    @staticmethod
    def build(window: DashboardWindow, data: DashboardReadData) -> ExecutiveDashboard:
        profits = {
            row.period: FinancialReportingService.consolidate(row.totals).net_profit
            for row in data.months
        }
        months = tuple(
            MonthlyProfit(period.label, profits.get(period.label, Money.zero()))
            for period in window.periods
        )
        previous, current = months[-2:]
        change = current.net_profit - previous.net_profit
        percentage = (
            (change.amount / abs(previous.net_profit.amount) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if not previous.net_profit.is_zero()
            else Decimal("0.00")
            if current.net_profit.is_zero()
            else None
        )
        districts = tuple(
            sorted(
                (
                    DistrictMetric(
                        row.district,
                        row.totals.total_events_settled,
                        FinancialReportingService.consolidate(row.totals).net_profit,
                    )
                    for row in data.districts
                ),
                key=lambda row: (-row.net_profit.amount, row.district),
            )
        )
        return ExecutiveDashboard(
            window.current.label,
            months,
            ProfitComparison(
                previous.period, current.net_profit, previous.net_profit, change, percentage
            ),
            tuple(sorted(data.packages, key=lambda row: (-row.events, row.name, row.package_id))),
            # Sin temática (theme_id None) va al final de cada empate, sin comparar etiquetas.
            tuple(
                sorted(
                    data.themes,
                    key=lambda row: (
                        -row.events,
                        row.theme_id is None,
                        row.name or "",
                        str(row.theme_id),
                    ),
                )
            ),
            tuple(sorted(data.extras, key=lambda row: (-row.times_hired, row.name, row.extra_id))),
            districts,
        )
