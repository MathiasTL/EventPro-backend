from __future__ import annotations

from app.domain.value_objects.service_category import (
    INVENTORY_SERVICE_CATEGORIES,
    ServiceCategory,
)


def test_all_categories() -> None:
    assert {c.value for c in ServiceCategory} == {"SHOW", "DJ", "DECORATION", "TENTS"}


def test_inventory_categories_subset() -> None:
    assert {
        ServiceCategory.DECORATION,
        ServiceCategory.TENTS,
    } == INVENTORY_SERVICE_CATEGORIES
