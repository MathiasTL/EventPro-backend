"""Fábricas compartidas por las pruebas del FinancialEngine y de Quote."""

from decimal import Decimal

from app.domain.services.financial_engine import FinancialEngine
from app.domain.value_objects.mobility import MobilityTariff
from app.domain.value_objects.money import Money


def pen(value: str) -> Money:
    return Money(Decimal(value))


def default_tariff(**changes: object) -> MobilityTariff:
    values: dict[str, object] = {
        "rate_per_km": pen("1.00"),
        "rate_per_minute": pen("0.30"),
        "minimum_amount": pen("20.00"),
        "margin_percent": Decimal("15"),
        "zone_1_amount": pen("25.00"),
        "zone_2_amount": pen("45.00"),
        "zone_3_amount": pen("70.00"),
    }
    values.update(changes)
    return MobilityTariff(**values)  # type: ignore[arg-type]


def default_engine(**tariff_changes: object) -> FinancialEngine:
    return FinancialEngine(tariff=default_tariff(**tariff_changes), advance_percent=10)
