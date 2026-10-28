"""Dobles y agregados exclusivos de US-22, sin infraestructura externa."""

from decimal import Decimal

from app.domain.value_objects.dashboard import DashboardReadData
from app.domain.value_objects.financial_reporting import FinancialTotals
from app.domain.value_objects.money import Money


def totals(profit="0", events=1):
    amount = Decimal(profit)
    return FinancialTotals(
        events,
        Money(max(amount, Decimal(0))),
        Money(max(-amount, Decimal(0))),
        Money.zero(),
        Money.zero(),
    )


class DashboardReadPort:
    def __init__(self, data=None):
        self.data = data or DashboardReadData()
        self.windows = []
        self.error = None

    async def get_dashboard(self, window):
        self.windows.append(window)
        if self.error:
            raise self.error
        return self.data
