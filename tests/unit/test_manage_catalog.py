"""Pruebas unitarias de ManageCatalogUseCase (RF-03, RF-04)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.use_cases.catalog.manage_catalog import ManageCatalogUseCase
from app.domain.exceptions.resource_exceptions import ResourceInUseError, ValidationError
from app.domain.value_objects.service_category import ServiceCategory


def _use_case() -> tuple[ManageCatalogUseCase, AsyncMock]:
    catalog = AsyncMock()
    return ManageCatalogUseCase(catalog), catalog


def test_create_package_validates_and_persists() -> None:
    use_case, catalog = _use_case()
    result = asyncio.run(
        use_case.create_package(
            name="Hora Loca Medium",
            service_category=ServiceCategory.SHOW,
            base_price=Decimal("750.00"),
            direct_cost=Decimal("400.00"),
            duration_minutes=60,
        )
    )
    assert result is catalog.create_package.return_value
    package = catalog.create_package.await_args.args[0]
    assert package.name == "Hora Loca Medium"
    assert package.base_price.amount == Decimal("750.00")
    assert package.duration_minutes == 60


def test_create_package_rejects_non_positive_price() -> None:
    use_case, catalog = _use_case()
    with pytest.raises(ValidationError):
        asyncio.run(
            use_case.create_package(
                name="Inválido",
                service_category=ServiceCategory.SHOW,
                base_price=Decimal("0.00"),
                direct_cost=Decimal("0.00"),
                duration_minutes=60,
            )
        )
    catalog.create_package.assert_not_awaited()


def test_create_inventory_item_rejects_show_category() -> None:
    use_case, catalog = _use_case()
    with pytest.raises(ValidationError):
        asyncio.run(
            use_case.create_inventory_item(
                name="No válido",
                service_category=ServiceCategory.SHOW,
                total_stock=1,
            )
        )
    catalog.create_inventory_item.assert_not_awaited()


def test_set_package_inventory_items_rejects_non_positive_quantity() -> None:
    use_case, catalog = _use_case()
    with pytest.raises(ValidationError):
        asyncio.run(use_case.set_package_inventory_items(uuid4(), [(uuid4(), 0)]))
    catalog.set_package_inventory_items.assert_not_awaited()


def test_update_inventory_item_rejects_stock_below_reservations() -> None:
    use_case, catalog = _use_case()
    catalog.count_future_reserved_units.return_value = 4
    with pytest.raises(ResourceInUseError):
        asyncio.run(
            use_case.update_inventory_item(
                uuid4(),
                name="Toldo Estándar 3x3 m",
                service_category=ServiceCategory.TENTS,
                total_stock=2,
            )
        )
    catalog.update_inventory_item.assert_not_awaited()


def test_update_inventory_item_allows_stock_covering_reservations() -> None:
    use_case, catalog = _use_case()
    catalog.count_future_reserved_units.return_value = 4
    result = asyncio.run(
        use_case.update_inventory_item(
            uuid4(),
            name="Toldo Estándar 3x3 m",
            service_category=ServiceCategory.TENTS,
            total_stock=6,
        )
    )
    assert result is catalog.update_inventory_item.return_value


def test_deactivate_inventory_item_rejects_when_in_use() -> None:
    use_case, catalog = _use_case()
    catalog.count_active_package_usage.return_value = 1
    with pytest.raises(ResourceInUseError):
        asyncio.run(use_case.deactivate_inventory_item(uuid4()))
    catalog.deactivate_inventory_item.assert_not_awaited()


def test_deactivate_inventory_item_rejects_when_reserved() -> None:
    use_case, catalog = _use_case()
    catalog.count_active_package_usage.return_value = 0
    catalog.count_future_reserved_units.return_value = 2
    with pytest.raises(ResourceInUseError):
        asyncio.run(use_case.deactivate_inventory_item(uuid4()))
    catalog.deactivate_inventory_item.assert_not_awaited()


def test_deactivate_inventory_item_when_free() -> None:
    use_case, catalog = _use_case()
    catalog.count_active_package_usage.return_value = 0
    catalog.count_future_reserved_units.return_value = 0
    result = asyncio.run(use_case.deactivate_inventory_item(uuid4()))
    assert result is catalog.deactivate_inventory_item.return_value
