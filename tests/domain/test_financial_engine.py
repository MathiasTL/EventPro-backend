from decimal import Decimal

import pytest

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.services.financial_engine import FinancialEngine
from app.domain.value_objects.liquidation import ExtraCharge, Liquidation
from app.domain.value_objects.mobility import MobilityZone, RouteEstimate
from app.domain.value_objects.money import Money

from .financial_support import default_engine, default_tariff, pen


def test_us06_vector_with_extras_and_mobility() -> None:
    # Paquete 1000 + extras 200, movilidad 100 -> total 1300, adelanto 120, saldo 1180.
    result = default_engine().liquidate(
        package_price=pen("1000.00"),
        extras=[ExtraCharge(pen("200.00"), 1)],
        mobility_amount=pen("100.00"),
    )
    assert result.services_subtotal == pen("1200.00")
    assert result.mobility_amount == pen("100.00")
    assert result.total_amount == pen("1300.00")
    assert result.advance_amount == pen("120.00")
    assert result.pending_balance == pen("1180.00")
    assert result.balance_services == pen("1080.00")
    assert result.balance_mobility == pen("100.00")


def test_api_example_vector_without_extras() -> None:
    # Paquete 1000, movilidad 80.50 -> total 1080.50, adelanto 100.00, saldo 980.50.
    result = default_engine().liquidate(
        package_price=pen("1000.00"), extras=[], mobility_amount=pen("80.50")
    )
    assert result.total_amount == pen("1080.50")
    assert result.advance_amount == pen("100.00")
    assert result.pending_balance == pen("980.50")
    assert result.balance_services == pen("900.00")
    assert result.balance_mobility == pen("80.50")


def test_advance_excludes_mobility_and_balance_keeps_it_whole() -> None:
    result = default_engine().liquidate(
        package_price=pen("500.00"), extras=[], mobility_amount=pen("300.00")
    )
    assert result.advance_amount == pen("50.00")
    assert result.pending_balance == pen("750.00")
    assert result.balance_services + result.balance_mobility == result.pending_balance


def test_extra_with_quantity_greater_than_one_multiplies_unit_price() -> None:
    result = default_engine().liquidate(
        package_price=pen("1000.00"),
        extras=[ExtraCharge(pen("50.25"), 3), ExtraCharge(pen("10.00"), 2)],
        mobility_amount=pen("0.00"),
    )
    assert result.services_subtotal == pen("1170.75")
    assert result.advance_amount == pen("117.08")  # 117.075 -> HALF_UP
    assert result.total_amount == pen("1170.75")


def test_zero_price_extra_is_accepted_and_changes_nothing() -> None:
    base = default_engine().liquidate(
        package_price=pen("1000.00"), extras=[], mobility_amount=pen("80.50")
    )
    with_free_extra = default_engine().liquidate(
        package_price=pen("1000.00"),
        extras=[ExtraCharge(pen("0.00"), 4)],
        mobility_amount=pen("80.50"),
    )
    assert with_free_extra == base


def test_advance_rounds_half_up_not_bankers() -> None:
    # 1000.05 * 10 % = 100.005 -> 100.01 (el redondeo bancario daria 100.00)
    result = default_engine().liquidate(
        package_price=pen("1000.05"), extras=[], mobility_amount=pen("0.00")
    )
    assert result.advance_amount == pen("100.01")
    assert result.pending_balance == pen("900.04")


def test_non_default_advance_percent() -> None:
    engine = FinancialEngine(tariff=default_tariff(), advance_percent=25)
    result = engine.liquidate(package_price=pen("400.00"), extras=[], mobility_amount=pen("40.00"))
    assert result.advance_amount == pen("100.00")
    assert result.pending_balance == pen("340.00")


def test_mobility_exemption_flows_into_liquidation() -> None:
    engine = default_engine()
    mobility = engine.resolve_mobility(
        client_provides_mobility=True,
        estimate=RouteEstimate(Decimal("20.00"), 30),
        zone=MobilityZone.ZONE_3,
    )
    result = engine.liquidate(
        package_price=pen("1000.00"), extras=[], mobility_amount=mobility.final_amount
    )
    assert result.mobility_amount == pen("0.00")
    assert result.total_amount == pen("1000.00")
    assert result.pending_balance == pen("900.00")


def test_estimator_result_flows_into_liquidation() -> None:
    engine = default_engine()
    mobility = engine.resolve_mobility(
        client_provides_mobility=False,
        estimate=RouteEstimate(Decimal("20.00"), 30),
        zone=MobilityZone.ZONE_1,
    )
    result = engine.liquidate(
        package_price=pen("1000.00"), extras=[], mobility_amount=mobility.final_amount
    )
    assert result.mobility_amount == pen("33.35")
    assert result.total_amount == pen("1033.35")


@pytest.mark.parametrize("price", ["0.00", "-10.00"])
def test_liquidate_rejects_non_positive_package_price(price: str) -> None:
    with pytest.raises(ValidationError):
        default_engine().liquidate(package_price=pen(price), extras=[], mobility_amount=pen("0"))


def test_liquidate_rejects_negative_mobility() -> None:
    with pytest.raises(ValidationError):
        default_engine().liquidate(
            package_price=pen("100.00"), extras=[], mobility_amount=pen("-0.01")
        )


def test_liquidate_rejects_other_currencies() -> None:
    with pytest.raises(ValidationError):
        default_engine().liquidate(
            package_price=Money(Decimal("100.00"), "USD"), extras=[], mobility_amount=pen("0")
        )
    with pytest.raises(ValidationError):
        default_engine().liquidate(
            package_price=pen("100.00"),
            extras=[],
            mobility_amount=Money(Decimal("1.00"), "USD"),
        )


def test_extra_charge_validations() -> None:
    with pytest.raises(ValidationError):
        ExtraCharge(pen("-1.00"), 1)
    with pytest.raises(ValidationError):
        ExtraCharge(pen("10.00"), 0)
    with pytest.raises(ValidationError):
        ExtraCharge(pen("10.00"), -2)
    with pytest.raises(ValidationError):
        ExtraCharge(pen("10.00"), True)
    with pytest.raises(ValidationError):
        ExtraCharge(pen("10.00"), 1.5)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ExtraCharge(Money(Decimal("1.00"), "USD"), 1)
    with pytest.raises(ValidationError):
        ExtraCharge(1.0, 1)  # type: ignore[arg-type]


def test_extra_charge_subtotal() -> None:
    assert ExtraCharge(pen("33.33"), 3).subtotal == pen("99.99")


def test_liquidation_rejects_negative_or_foreign_amounts() -> None:
    zero = pen("0.00")
    with pytest.raises(ValidationError):
        Liquidation(
            services_subtotal=pen("-1.00"),
            mobility_amount=zero,
            total_amount=zero,
            advance_amount=zero,
            pending_balance=zero,
            balance_services=zero,
            balance_mobility=zero,
        )
    with pytest.raises(ValidationError):
        Liquidation(
            services_subtotal=zero,
            mobility_amount=Money(Decimal("1.00"), "USD"),
            total_amount=zero,
            advance_amount=zero,
            pending_balance=zero,
            balance_services=zero,
            balance_mobility=zero,
        )
