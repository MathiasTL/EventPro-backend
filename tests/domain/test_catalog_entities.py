from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.entities.catalog import Crew, Extra, InventoryItem, Package, Theme
from app.domain.exceptions.resource_exceptions import (
    InvalidServiceCategoryError,
    ValidationError,
)
from app.domain.value_objects.money import Money
from app.domain.value_objects.service_category import ServiceCategory


def _money(value: str) -> Money:
    return Money(Decimal(value))


def test_package_valid_and_deactivate() -> None:
    package = Package(
        name="Hora Loca Medium",
        service_category=ServiceCategory.SHOW,
        base_price=_money("750.00"),
        direct_cost=_money("400.00"),
        duration_minutes=60,
    )
    assert package.is_active is True
    package.deactivate()
    assert package.is_active is False


def test_package_rejects_non_positive_price() -> None:
    with pytest.raises(ValidationError):
        Package(
            name="Inválido",
            service_category=ServiceCategory.SHOW,
            base_price=_money("0.00"),
            direct_cost=_money("0.00"),
        )


def test_package_rejects_non_positive_duration() -> None:
    with pytest.raises(ValidationError):
        Package(
            name="Inválido",
            service_category=ServiceCategory.SHOW,
            base_price=_money("10.00"),
            direct_cost=_money("0.00"),
            duration_minutes=0,
        )


def test_package_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Package(
            name="   ",
            service_category=ServiceCategory.SHOW,
            base_price=_money("10.00"),
            direct_cost=_money("0.00"),
        )


def test_theme_requires_name_and_deactivates() -> None:
    with pytest.raises(ValidationError):
        Theme(name="")
    theme = Theme(name="Selva")
    assert theme.is_active is True
    theme.deactivate()
    assert theme.is_active is False


def test_extra_validates_prices_and_deactivates() -> None:
    extra = Extra(name="Gorila", sale_price=_money("250.00"), direct_cost=_money("120.00"))
    assert extra.sale_price.amount == Decimal("250.00")
    extra.deactivate()
    assert extra.is_active is False
    with pytest.raises(ValidationError):
        Extra(name="Malo", sale_price=_money("-1.00"), direct_cost=_money("0.00"))


def test_inventory_item_restricts_category() -> None:
    item = InventoryItem(
        name="Toldo Estándar 3x3 m",
        service_category=ServiceCategory.TENTS,
        total_stock=10,
    )
    assert item.total_stock == 10
    with pytest.raises(InvalidServiceCategoryError):
        InventoryItem(
            name="Show como inventario",
            service_category=ServiceCategory.SHOW,
            total_stock=1,
        )


def test_inventory_item_rejects_negative_stock_and_deactivates() -> None:
    with pytest.raises(ValidationError):
        InventoryItem(
            name="Toldo",
            service_category=ServiceCategory.TENTS,
            total_stock=-1,
        )
    item = InventoryItem(
        name="Toldo",
        service_category=ServiceCategory.TENTS,
        total_stock=1,
    )
    item.deactivate()
    assert item.is_active is False


def test_crew_validates_leader_and_phone() -> None:
    with pytest.raises(ValidationError):
        Crew(leader_name="", phone="+51955666777", service_category=ServiceCategory.SHOW)
    with pytest.raises(ValidationError):
        Crew(leader_name="Luis", phone="", service_category=ServiceCategory.SHOW)


def test_crew_link_and_unlink_user() -> None:
    crew = Crew(
        leader_name="Luis Torres",
        phone="+51955666777",
        service_category=ServiceCategory.SHOW,
    )
    assert crew.user_id is None
    user_id = crew.id
    crew.link_user(user_id)
    assert crew.user_id == user_id
    crew.unlink_user()
    assert crew.user_id is None
    crew.deactivate()
    assert crew.is_active is False
