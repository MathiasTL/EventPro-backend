from decimal import Decimal

import pytest

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.services.financial_engine import FinancialEngine
from app.domain.value_objects.mobility import (
    MobilityScenario,
    MobilityZone,
    RouteEstimate,
    RouteLocation,
)

from .financial_support import default_engine, default_tariff, pen


def test_route_estimate_quantizes_distance_half_up() -> None:
    assert RouteEstimate(Decimal("12.345"), 10).distance_km == Decimal("12.35")
    assert RouteEstimate(Decimal("12.344"), 10).distance_km == Decimal("12.34")


@pytest.mark.parametrize(
    ("distance", "minutes"),
    [
        (Decimal("-0.01"), 10),
        (Decimal("5"), -1),
        (Decimal("10000"), 10),
        (Decimal("NaN"), 10),
        (Decimal("Infinity"), 10),
    ],
)
def test_route_estimate_rejects_invalid_values(distance: Decimal, minutes: int) -> None:
    with pytest.raises(ValidationError):
        RouteEstimate(distance, minutes)


@pytest.mark.parametrize(
    ("distance", "minutes"), [(10.5, 10), (Decimal("5"), 10.5), (Decimal("5"), True)]
)
def test_route_estimate_rejects_wrong_types(distance: object, minutes: object) -> None:
    with pytest.raises(ValidationError):
        RouteEstimate(distance, minutes)  # type: ignore[arg-type]


def test_route_location_accepts_address_coordinates_or_both() -> None:
    assert RouteLocation(address="  Av. Arequipa 123 ").address == "Av. Arequipa 123"
    assert (
        RouteLocation(latitude=Decimal("-12.0864"), longitude=Decimal("-77.0328")).address is None
    )
    assert RouteLocation(address="Base", latitude=Decimal("-12.0"), longitude=Decimal("-77.0"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"address": "   "},
        {"latitude": Decimal("-12.0")},
        {"longitude": Decimal("-77.0")},
        {"latitude": Decimal("91"), "longitude": Decimal("-77.0")},
        {"latitude": Decimal("-12.0"), "longitude": Decimal("181")},
    ],
)
def test_route_location_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RouteLocation(**kwargs)  # type: ignore[arg-type]


def test_tariff_zone_amounts() -> None:
    tariff = default_tariff()
    assert tariff.zone_amount(MobilityZone.ZONE_1) == pen("25.00")
    assert tariff.zone_amount(MobilityZone.ZONE_2) == pen("45.00")
    assert tariff.zone_amount(MobilityZone.ZONE_3) == pen("70.00")


@pytest.mark.parametrize(
    "changes",
    [
        {"rate_per_km": pen("-0.01")},
        {"zone_3_amount": pen("-1.00")},
        {"margin_percent": Decimal("-1")},
        {"margin_percent": 15},
        {"minimum_amount": 20},
    ],
)
def test_tariff_rejects_invalid_values(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        default_tariff(**changes)


def test_tariff_rejects_non_pen_currency() -> None:
    from app.domain.value_objects.money import Money

    with pytest.raises(ValidationError):
        default_tariff(rate_per_km=Money(Decimal("1.00"), "USD"))


def test_route_scenario_applies_rates_and_margin() -> None:
    # 20 km * 1.00 + 30 min * 0.30 = 29.00; con margen 15 % = 33.35
    result = default_engine().mobility(RouteEstimate(Decimal("20.00"), 30))
    assert result.scenario is MobilityScenario.ROUTE
    assert result.distance_km == Decimal("20.00")
    assert result.duration_minutes == 30
    assert result.base_amount == pen("29.00")
    assert result.final_amount == pen("33.35")


def test_route_scenario_applies_minimum_before_margin() -> None:
    # 5 km * 1.00 + 5 min * 0.30 = 6.50, menor que el mínimo 20.00 -> 20.00 * 1.15 = 23.00
    result = default_engine().mobility(RouteEstimate(Decimal("5.00"), 5))
    assert result.base_amount == pen("20.00")
    assert result.final_amount == pen("23.00")


def test_route_scenario_zero_route_charges_minimum() -> None:
    result = default_engine().mobility(RouteEstimate(Decimal("0"), 0))
    assert result.base_amount == pen("20.00")
    assert result.final_amount == pen("23.00")


def test_route_scenario_rounds_half_up_not_bankers() -> None:
    # base 0.30 * 1.15 = 0.345 -> 0.35 con ROUND_HALF_UP (0.34 con redondeo bancario)
    engine = default_engine(minimum_amount=pen("0.00"), rate_per_minute=pen("0.00"))
    result = engine.mobility(RouteEstimate(Decimal("0.30"), 0))
    assert result.base_amount == pen("0.30")
    assert result.final_amount == pen("0.35")


def test_route_scenario_uses_the_quantized_kilometers() -> None:
    # 12.345 km se cuantiza a 12.35 km antes de calcular: 12.35 + 0.00 = 12.35 -> mínimo 20.00
    estimate = RouteEstimate(Decimal("12.345"), 0)
    engine = default_engine(minimum_amount=pen("0.00"), rate_per_minute=pen("0.00"))
    result = engine.mobility(estimate)
    assert result.distance_km == Decimal("12.35")
    assert result.base_amount == pen("12.35")
    assert result.final_amount == pen("14.20")  # 12.35 * 1.15 = 14.2025


def test_contingency_uses_zone_amount_without_margin() -> None:
    result = default_engine().contingency(MobilityZone.ZONE_2)
    assert result.scenario is MobilityScenario.CONTINGENCY
    assert result.distance_km is None
    assert result.duration_minutes is None
    assert result.base_amount == pen("45.00")
    assert result.final_amount == pen("45.00")


def test_resolve_mobility_exempt_wins_over_estimate_and_zone() -> None:
    engine = default_engine()
    result = engine.resolve_mobility(
        client_provides_mobility=True,
        estimate=RouteEstimate(Decimal("20.00"), 30),
        zone=MobilityZone.ZONE_3,
    )
    assert result.scenario is MobilityScenario.EXEMPT
    assert result.final_amount == pen("0.00")
    assert result.base_amount == pen("0.00")
    assert result.distance_km is None
    assert result.duration_minutes is None


def test_resolve_mobility_prefers_estimate_over_zone() -> None:
    result = default_engine().resolve_mobility(
        client_provides_mobility=False,
        estimate=RouteEstimate(Decimal("20.00"), 30),
        zone=MobilityZone.ZONE_3,
    )
    assert result.scenario is MobilityScenario.ROUTE
    assert result.final_amount == pen("33.35")


def test_resolve_mobility_falls_back_to_zone_when_estimator_failed() -> None:
    result = default_engine().resolve_mobility(
        client_provides_mobility=False, estimate=None, zone=MobilityZone.ZONE_3
    )
    assert result.scenario is MobilityScenario.CONTINGENCY
    assert result.final_amount == pen("70.00")


@pytest.mark.parametrize("percent", [0, 101, -5, True, 10.5])
def test_engine_rejects_invalid_advance_percent(percent: object) -> None:
    with pytest.raises(ValidationError):
        FinancialEngine(tariff=default_tariff(), advance_percent=percent)  # type: ignore[arg-type]
