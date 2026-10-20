"""Consolidación financiera pura: RN-08, sin persistencia ni frameworks."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.domain.entities.event import Event
from app.domain.value_objects.financial_reporting import (
    EventDirectCosts,
    EventFinancialSnapshot,
    FinancialPnl,
    FinancialTotals,
)
from app.domain.value_objects.money import Money


class FinancialReportingService:
    @staticmethod
    def consolidate(totals: FinancialTotals) -> FinancialPnl:
        costs = (
            totals.fixed_packages_cost + totals.fixed_extras_cost + totals.mobility_operational_cost
        )
        profit = totals.gross_revenue - costs
        margin = (
            (profit.amount / totals.gross_revenue.amount * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if not totals.gross_revenue.is_zero()
            else Decimal("0.00")
        )
        return FinancialPnl(totals, costs, profit, margin)

    @staticmethod
    def snapshot(
        event: Event,
        costs: EventDirectCosts,
        verified_extension_amount: Money,
        recorded_at: datetime,
    ) -> EventFinancialSnapshot:
        return EventFinancialSnapshot(
            event.id,
            event.advance_paid
            + event.pre_show_balance_paid
            + event.legacy_extra_hours_amount
            + verified_extension_amount,
            costs,
            event.advance_paid,
            event.pre_show_balance_paid,
            event.legacy_extra_hours_amount,
            verified_extension_amount,
            recorded_at,
        )
