"""Pruebas unitarias del adaptador de disponibilidad (sin base de datos)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from app.application.dtos.availability_dto import (
    AvailabilityRequest,
    AvailabilityStatus,
    CrewTransitRequest,
)
from app.domain.services.concurrency_evaluator import ConcurrencyEvaluator
from app.domain.services.inventory_availability import InventoryAvailabilityService
from app.domain.services.travel_interval_service import TravelIntervalService
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.availability import AvailabilityAdapter
from app.infrastructure.adapters.secondary.cache import InMemoryLockAdapter
from app.infrastructure.adapters.secondary.persistence import (
    EventWindowRow,
    InventoryRequirementRow,
)
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)

_DAY = date(2026, 12, 24)
_BASE = datetime(2026, 12, 24, 20, 0, tzinfo=UTC)


def _window(start_offset: int, duration: int) -> TimeWindow:
    start = _BASE + timedelta(minutes=start_offset)
    return TimeWindow(start, start + timedelta(minutes=duration))


def _reservation(
    item_id: UUID,
    quantity: int,
    start_offset: int,
    duration: int,
    status: str = "ACTIVE",
) -> InventoryReservationModel:
    window = _window(start_offset, duration)
    return InventoryReservationModel(
        id=uuid4(),
        event_id=uuid4(),
        inventory_item_id=item_id,
        quantity=quantity,
        starts_at=window.start,
        ends_at=window.end,
        status=status,
    )


class FakeAvailabilityRepository:
    def __init__(
        self,
        requirements: tuple[InventoryRequirementRow, ...] = (),
        reservations: tuple[InventoryReservationModel, ...] = (),
        events: tuple[EventWindowRow, ...] = (),
    ) -> None:
        self._requirements = requirements
        self._reservations = reservations
        self._events = events

    async def get_package_inventory_requirements(
        self, package_id: UUID
    ) -> tuple[InventoryRequirementRow, ...]:
        return self._requirements

    async def list_active_reservations(
        self, inventory_item_ids: list[UUID], window: TimeWindow
    ) -> tuple[InventoryReservationModel, ...]:
        wanted = set(inventory_item_ids)
        return tuple(
            reservation
            for reservation in self._reservations
            if reservation.inventory_item_id in wanted
            and reservation.status == "ACTIVE"
            and reservation.starts_at < window.end
            and reservation.ends_at > window.start
        )

    async def list_countable_events(self, window: TimeWindow) -> tuple[EventWindowRow, ...]:
        return tuple(row for row in self._events if row.window.overlaps(window))


class RecordingLock(InMemoryLockAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.released: list[str] = []

    async def release(self, key: str) -> None:
        self.released.append(key)
        await super().release(key)


def _adapter(
    repository: FakeAvailabilityRepository, lock: InMemoryLockAdapter | None = None
) -> AvailabilityAdapter:
    return AvailabilityAdapter(
        repository=repository,
        lock=lock or InMemoryLockAdapter(),
        concurrency_evaluator=ConcurrencyEvaluator(threshold=2),
        inventory_availability=InventoryAvailabilityService(),
        travel_interval_service=TravelIntervalService(),
    )


def _request(package_id: UUID | None = None, duration: int = 60) -> AvailabilityRequest:
    return AvailabilityRequest(
        event_date=_DAY,
        start_time=time(20, 0),
        duration_minutes=duration,
        package_id=package_id or uuid4(),
    )


def test_available_when_package_consumes_no_inventory() -> None:
    result = asyncio.run(_adapter(FakeAvailabilityRepository()).check_availability(_request()))
    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.simultaneous_count == 1
    assert result.shortages == ()


def test_conflict_when_stock_does_not_cover_requirements() -> None:
    item = uuid4()
    repository = FakeAvailabilityRepository(
        requirements=(InventoryRequirementRow(item, 3, total_stock=2, name="Toldo"),)
    )
    result = asyncio.run(_adapter(repository).check_availability(_request()))
    assert result.status is AvailabilityStatus.CONFLICT
    assert result.shortages[0].requested == 3
    assert result.shortages[0].available == 2
    assert result.shortages[0].inventory_item_id == item


def test_available_when_active_reservations_leave_enough_stock() -> None:
    item = uuid4()
    repository = FakeAvailabilityRepository(
        requirements=(InventoryRequirementRow(item, 2, total_stock=5, name="Toldo"),),
        reservations=(_reservation(item, 3, start_offset=60, duration=60),),
    )
    result = asyncio.run(_adapter(repository).check_availability(_request()))
    assert result.status is AvailabilityStatus.AVAILABLE


def test_conflict_when_active_reservation_consumes_stock() -> None:
    item = uuid4()
    repository = FakeAvailabilityRepository(
        requirements=(InventoryRequirementRow(item, 3, total_stock=5, name="Toldo"),),
        reservations=(_reservation(item, 3, start_offset=0, duration=120),),
    )
    result = asyncio.run(_adapter(repository).check_availability(_request()))
    assert result.status is AvailabilityStatus.CONFLICT
    assert result.shortages[0].available == 2


def test_released_reservations_do_not_consume_stock() -> None:
    item = uuid4()
    repository = FakeAvailabilityRepository(
        requirements=(InventoryRequirementRow(item, 3, total_stock=5, name="Toldo"),),
        reservations=(_reservation(item, 3, start_offset=0, duration=120, status="RELEASED"),),
    )
    result = asyncio.run(_adapter(repository).check_availability(_request()))
    assert result.status is AvailabilityStatus.AVAILABLE


def test_threshold_exceeded_requires_manual_approval() -> None:
    repository = FakeAvailabilityRepository(
        events=(
            EventWindowRow(uuid4(), "SCHEDULED", _window(-60, 120)),
            EventWindowRow(uuid4(), "SCHEDULED", _window(-30, 120)),
        )
    )
    result = asyncio.run(_adapter(repository).check_availability(_request()))
    # 2 existentes + el candidato = 3 > umbral configurado (2).
    assert result.status is AvailabilityStatus.REQUIRES_MANUAL_APPROVAL
    assert result.simultaneous_count == 3


def test_adjacent_events_do_not_count_for_threshold() -> None:
    repository = FakeAvailabilityRepository(
        events=(EventWindowRow(uuid4(), "SCHEDULED", _window(-120, 120)),),
    )
    result = asyncio.run(_adapter(repository).check_availability(_request()))
    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.simultaneous_count == 1


def test_conflict_takes_precedence_over_threshold() -> None:
    item = uuid4()
    repository = FakeAvailabilityRepository(
        requirements=(InventoryRequirementRow(item, 3, total_stock=1, name="Toldo"),),
        events=(
            EventWindowRow(uuid4(), "SCHEDULED", _window(-60, 120)),
            EventWindowRow(uuid4(), "SCHEDULED", _window(-30, 120)),
        ),
    )
    result = asyncio.run(_adapter(repository).check_availability(_request()))
    assert result.status is AvailabilityStatus.CONFLICT
    assert result.simultaneous_count == 3
    assert len(result.shortages) == 1


def test_lock_is_released_after_check() -> None:
    lock = RecordingLock()
    repository = FakeAvailabilityRepository()
    asyncio.run(_adapter(repository, lock).check_availability(_request()))
    assert len(lock.released) == 1
    assert not lock.is_locked(lock.released[0])


def test_crew_transit_feasible_and_infeasible() -> None:
    adapter = _adapter(FakeAvailabilityRepository())
    previous_end = _BASE
    feasible = asyncio.run(
        adapter.check_crew_transit(
            CrewTransitRequest(
                crew_id=uuid4(),
                previous_end=previous_end,
                candidate_start=previous_end + timedelta(minutes=105),
                transit_minutes=75,
            )
        )
    )
    assert feasible.feasible
    assert feasible.required_minutes == 105
    assert feasible.available_gap_minutes == 105

    infeasible = asyncio.run(
        adapter.check_crew_transit(
            CrewTransitRequest(
                crew_id=uuid4(),
                previous_end=previous_end,
                candidate_start=previous_end + timedelta(minutes=104),
                transit_minutes=75,
            )
        )
    )
    assert not infeasible.feasible
    assert infeasible.available_gap_minutes == 104


def test_crew_transit_override_shortens_required_interval() -> None:
    adapter = _adapter(FakeAvailabilityRepository())
    previous_end = _BASE
    result = asyncio.run(
        adapter.check_crew_transit(
            CrewTransitRequest(
                crew_id=uuid4(),
                previous_end=previous_end,
                candidate_start=previous_end + timedelta(minutes=60),
                transit_minutes=75,
                override_minutes=60,
            )
        )
    )
    assert result.feasible
    assert result.required_minutes == 60
