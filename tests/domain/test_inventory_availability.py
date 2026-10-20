from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.domain.services.inventory_availability import (
    InventoryAvailabilityService,
    InventoryRequest,
    InventoryReservation,
)
from app.domain.value_objects.time_window import TimeWindow

_BASE = datetime(2026, 10, 5, 18, 0)


def _window(start_minutes: int, duration_minutes: int) -> TimeWindow:
    start = _BASE + timedelta(minutes=start_minutes)
    return TimeWindow(start, start + timedelta(minutes=duration_minutes))


def _reservation(
    item_id: UUID, quantity: int, start_minutes: int, duration: int = 120
) -> InventoryReservation:
    return InventoryReservation(
        inventory_item_id=item_id,
        quantity=quantity,
        window=_window(start_minutes, duration),
    )


def test_positive_quantities_required() -> None:
    with pytest.raises(ValueError):
        InventoryReservation(inventory_item_id=uuid4(), quantity=0, window=_window(0, 60))
    with pytest.raises(ValueError):
        InventoryRequest(inventory_item_id=uuid4(), quantity=-1, window=_window(0, 60))


def test_overlapping_reservations_reduce_stock() -> None:
    service = InventoryAvailabilityService()
    item = uuid4()
    reservations = (_reservation(item, 2, 0), _reservation(item, 1, 60))
    assert service.reserved_quantity(item, reservations, _window(0, 120)) == 3
    assert service.available_quantity(10, item, reservations, _window(0, 120)) == 7


def test_non_overlapping_reservations_do_not_reduce_stock() -> None:
    service = InventoryAvailabilityService()
    item = uuid4()
    reservations = (_reservation(item, 2, 0, duration=60),)
    assert service.available_quantity(10, item, reservations, _window(120, 60)) == 10


def test_adjacent_reservations_do_not_overlap() -> None:
    service = InventoryAvailabilityService()
    item = uuid4()
    reservations = (_reservation(item, 5, 0, duration=60),)
    assert service.reserved_quantity(item, reservations, _window(60, 60)) == 0


def test_other_items_are_ignored() -> None:
    service = InventoryAvailabilityService()
    item, other = uuid4(), uuid4()
    reservations = (_reservation(other, 9, 0),)
    assert service.reserved_quantity(item, reservations, _window(0, 60)) == 0


def test_check_available_and_shortage() -> None:
    service = InventoryAvailabilityService()
    item = uuid4()
    reservations = (_reservation(item, 8, 0),)

    available = service.check(10, reservations, InventoryRequest(item, 2, _window(0, 60)))
    assert available.is_available
    assert available.available_quantity == 2
    assert available.missing_quantity == 0

    shortage = service.check(10, reservations, InventoryRequest(item, 3, _window(0, 60)))
    assert not shortage.is_available
    assert shortage.missing_quantity == 1


def test_available_quantity_never_negative() -> None:
    service = InventoryAvailabilityService()
    item = uuid4()
    reservations = (_reservation(item, 50, 0),)
    assert service.available_quantity(10, item, reservations, _window(0, 60)) == 0


def test_negative_total_stock_rejected() -> None:
    with pytest.raises(ValueError):
        InventoryAvailabilityService().available_quantity(-1, uuid4(), (), _window(0, 60))
