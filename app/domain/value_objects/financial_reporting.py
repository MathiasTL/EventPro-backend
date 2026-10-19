"""Períodos y componentes contables inmutables de US-21, sin dependencias externas."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.money import Money


class PeriodType(StrEnum):
    MONTHLY = "MONTHLY"
    WEEKLY = "WEEKLY"


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_financial_amount(amount: Money) -> None:
    if (
        not isinstance(amount, Money)
        or amount.currency != "PEN"
        or not amount.amount.is_finite()
        or amount.amount < 0
    ):
        raise FinancialDataInconsistentError(
            "Los importes deben ser finitos y no negativos en PEN."
        )


@dataclass(frozen=True)
class AccountingPeriod:
    start: date
    end: date
    label: str

    @classmethod
    def create(
        cls,
        period_type: PeriodType,
        year: int,
        *,
        month: int | None = None,
        week: int | None = None,
    ) -> "AccountingPeriod":
        if not isinstance(period_type, PeriodType) or not _integer(year) or not 1 <= year <= 9998:
            raise ValidationError("period_type y year (1–9998) deben ser válidos.")
        if period_type is PeriodType.MONTHLY:
            if not _integer(month) or month is None or not 1 <= month <= 12 or week is not None:
                raise ValidationError("MONTHLY exige month (1–12) y no admite week.")
            return cls(
                date(year, month, 1),
                date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1),
                f"{year:04d}-{month:02d}",
            )
        if not _integer(week) or week is None or month is not None:
            raise ValidationError("WEEKLY exige week y no admite month.")
        try:
            start = date.fromisocalendar(year, week, 1)
        except ValueError as exc:
            raise ValidationError("La semana ISO no existe en el año indicado.") from exc
        return cls(start, start + timedelta(days=7), f"{year:04d}-W{week:02d}")


@dataclass(frozen=True)
class ExtraDirectCost:
    extra_id: UUID
    quantity: int
    unit_cost: Money

    def __post_init__(self) -> None:
        if not _integer(self.quantity) or self.quantity <= 0:
            raise FinancialDataInconsistentError(
                "La cantidad de extras debe ser un entero positivo."
            )
        validate_financial_amount(self.unit_cost)


@dataclass(frozen=True)
class EventDirectCosts:
    package_id: UUID
    package_cost: Money
    extras: tuple[ExtraDirectCost, ...]
    mobility_cost: Money

    def __post_init__(self) -> None:
        validate_financial_amount(self.package_cost)
        validate_financial_amount(self.mobility_cost)

    @property
    def extras_cost(self) -> Money:
        return sum((line.unit_cost * line.quantity for line in self.extras), Money.zero())


@dataclass(frozen=True)
class FinancialTotals:
    total_events_settled: int
    gross_revenue: Money
    fixed_packages_cost: Money
    fixed_extras_cost: Money
    mobility_operational_cost: Money

    def __post_init__(self) -> None:
        if not _integer(self.total_events_settled) or self.total_events_settled < 0:
            raise FinancialDataInconsistentError("El contador de eventos debe ser no negativo.")
        for amount in (
            self.gross_revenue,
            self.fixed_packages_cost,
            self.fixed_extras_cost,
            self.mobility_operational_cost,
        ):
            validate_financial_amount(amount)


@dataclass(frozen=True)
class FinancialPnl:
    totals: FinancialTotals
    total_costs: Money
    net_profit: Money
    profit_margin_percentage: Decimal


@dataclass(frozen=True)
class EventFinancialSnapshot:
    event_id: UUID
    gross_revenue: Money
    costs: EventDirectCosts
    advance_paid: Money
    pre_show_balance_paid: Money
    legacy_extra_hours_amount: Money
    verified_extension_amount: Money
    recorded_at: datetime

    def __post_init__(self) -> None:
        for amount in (
            self.gross_revenue,
            self.advance_paid,
            self.pre_show_balance_paid,
            self.legacy_extra_hours_amount,
            self.verified_extension_amount,
        ):
            validate_financial_amount(amount)
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise FinancialDataInconsistentError("La captura requiere fecha con zona horaria.")
        object.__setattr__(self, "recorded_at", self.recorded_at.astimezone(UTC))

    @property
    def fixed_extras_cost(self) -> Money:
        return self.costs.extras_cost
