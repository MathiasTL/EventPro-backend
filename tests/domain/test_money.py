from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.value_objects.money import Money


def test_money_quantizes_to_two_decimals() -> None:
    assert Money(Decimal("10.005")).amount == Decimal("10.01")
    assert Money(Decimal("10.004")).amount == Decimal("10.00")


def test_money_requires_decimal() -> None:
    with pytest.raises(TypeError):
        Money(10.0)  # type: ignore[arg-type]


def test_money_addition_and_subtraction() -> None:
    assert (Money(Decimal("10.00")) + Money(Decimal("2.50"))).amount == Decimal("12.50")
    assert (Money(Decimal("10.00")) - Money(Decimal("2.50"))).amount == Decimal("7.50")


def test_money_multiplication() -> None:
    assert (Money(Decimal("100.00")) * Decimal("0.10")).amount == Decimal("10.00")
    assert (2 * Money(Decimal("100.00"))).amount == Decimal("200.00")


def test_money_rejects_mixed_currencies() -> None:
    with pytest.raises(ValueError):
        Money(Decimal("10.00"), "PEN") + Money(Decimal("10.00"), "USD")


def test_money_zero_and_is_zero() -> None:
    assert Money.zero().is_zero()
    assert not Money(Decimal("0.01")).is_zero()


def test_money_comparisons() -> None:
    assert Money(Decimal("5.00")) < Money(Decimal("6.00"))
    assert Money(Decimal("5.00")) <= Money(Decimal("5.00"))
    assert Money(Decimal("7.00")) > Money(Decimal("6.00"))
    assert Money(Decimal("6.00")) >= Money(Decimal("6.00"))


def test_money_rejects_empty_currency() -> None:
    with pytest.raises(ValueError):
        Money(Decimal("10.00"), "")
