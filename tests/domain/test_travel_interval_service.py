from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.services.travel_interval_service import TravelIntervalService
from app.domain.value_objects.time_window import TimeWindow

_BASE = datetime(2026, 10, 5, 18, 0)


def _window(start_minutes: int, duration_minutes: int) -> TimeWindow:
    start = _BASE + timedelta(minutes=start_minutes)
    return TimeWindow(start, start + timedelta(minutes=duration_minutes))


def test_default_buffer() -> None:
    service = TravelIntervalService()
    assert service.rest_buffer_minutes == 30
    assert service.required_interval_minutes(45) == 75


def test_custom_buffer() -> None:
    service = TravelIntervalService(rest_buffer_minutes=15)
    assert service.required_interval_minutes(45) == 60


def test_negative_inputs_rejected() -> None:
    service = TravelIntervalService()
    with pytest.raises(ValueError):
        TravelIntervalService(rest_buffer_minutes=-1)
    with pytest.raises(ValueError):
        service.required_interval_minutes(-1)
    with pytest.raises(ValueError):
        service.required_interval_minutes(45, override_minutes=-1)


def test_override_replaces_computed_interval() -> None:
    service = TravelIntervalService()
    assert service.required_interval_minutes(45, override_minutes=35) == 35


def test_assignment_infeasible_when_gap_below_required() -> None:
    service = TravelIntervalService()
    # Show 18:00-19:00 en San Borja y otro 20:00 en Los Olivos; tránsito 75 min.
    previous = _window(0, 60)
    following = _window(120, 60)
    assert not service.is_feasible(previous, following, transit_minutes=75)


def test_assignment_feasible_when_gap_meets_required() -> None:
    service = TravelIntervalService()
    # Holgura de 90 min (19:00 -> 20:30); tránsito 60 + margen 30 = 90 exactos.
    previous = _window(0, 60)
    following = _window(150, 60)
    assert service.is_feasible(previous, following, transit_minutes=60)


def test_override_makes_infeasible_assignment_feasible() -> None:
    service = TravelIntervalService()
    previous = _window(0, 60)
    following = _window(120, 60)  # 120 min de holgura
    assert not service.is_feasible(previous, following, transit_minutes=45)
    assert service.is_feasible(previous, following, transit_minutes=45, override_minutes=30)


def test_overlapping_shows_are_never_feasible() -> None:
    service = TravelIntervalService()
    previous = _window(0, 60)
    following = _window(30, 60)
    assert not service.is_feasible(previous, following, transit_minutes=0, override_minutes=0)


def test_is_gap_feasible_uses_required_interval() -> None:
    service = TravelIntervalService()
    # 75 min de tránsito + 30 min de margen = 105 min requeridos.
    assert not service.is_gap_feasible(104, transit_minutes=75)
    assert service.is_gap_feasible(105, transit_minutes=75)
    assert service.is_gap_feasible(105, transit_minutes=75, override_minutes=105)
    assert not service.is_gap_feasible(104, transit_minutes=75, override_minutes=105)
