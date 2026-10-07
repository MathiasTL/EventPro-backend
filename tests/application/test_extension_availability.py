from datetime import timedelta
from uuid import uuid4

import pytest

from app.application.dtos.event_occupancy_dto import (
    CrewOccupancy,
    EventOccupancy,
    InventoryOccupancy,
)
from app.application.services.event_extension_availability import check_extension_availability
from app.domain.exceptions.event_exceptions import EventResourceConflictError
from app.domain.services.inventory_availability import InventoryRequest, InventoryReservation
from app.domain.value_objects.time_window import TimeWindow
from tests.event_support import make_event


@pytest.mark.parametrize(
    "interval, gap, rejected", [(None, 30, True), (31, 30, True), (30, 30, False)]
)
def test_uses_applied_transit_interval_and_rejects_unknown(interval, gap, rejected):
    event = make_event(extra_minutes_total=90)
    end = event.time_window.end
    following = TimeWindow(end + timedelta(minutes=gap), end + timedelta(hours=2))
    snapshot = EventOccupancy(crews=(CrewOccupancy(uuid4(), following, interval),))
    if rejected:
        with pytest.raises(EventResourceConflictError):
            check_extension_availability(event, snapshot, 3)
    else:
        check_extension_availability(event, snapshot, 3)


def test_crew_overlap_in_operational_window_is_rejected():
    event = make_event(extra_minutes_total=90)
    snapshot = EventOccupancy(crews=(CrewOccupancy(uuid4(), event.time_window, 0),))
    with pytest.raises(EventResourceConflictError, match="elenco"):
        check_extension_availability(event, snapshot, 3)


def test_stock_and_global_concurrency_conflicts_require_manual_resolution():
    event = make_event(extra_minutes_total=90)
    item = uuid4()
    inventory = InventoryOccupancy(
        1,
        InventoryRequest(item, 1, event.time_window),
        (InventoryReservation(item, 1, event.time_window),),
    )
    with pytest.raises(EventResourceConflictError, match="inventario"):
        check_extension_availability(event, EventOccupancy(inventory=(inventory,)), 3)
    with pytest.raises(EventResourceConflictError, match="aprobación manual"):
        check_extension_availability(event, EventOccupancy((event.time_window,)), 1)
