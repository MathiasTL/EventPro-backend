from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.value_objects.time_window import TimeWindow


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute)


def test_duration_and_validation() -> None:
    window = TimeWindow(_dt(18), _dt(19))
    assert window.duration_minutes == 60
    with pytest.raises(ValueError):
        TimeWindow(_dt(19), _dt(18))
    with pytest.raises(ValueError):
        TimeWindow(_dt(18), _dt(18))


def test_overlaps_half_open_interval() -> None:
    assert TimeWindow(_dt(18), _dt(19)).overlaps(TimeWindow(_dt(18, 30), _dt(19, 30)))
    assert TimeWindow(_dt(18), _dt(19)).overlaps(TimeWindow(_dt(17), _dt(18, 30)))


def test_adjacent_windows_do_not_overlap() -> None:
    first = TimeWindow(_dt(18), _dt(19))
    second = TimeWindow(_dt(19), _dt(20))
    assert not first.overlaps(second)
    assert first.is_adjacent(second)


def test_disjoint_windows_do_not_overlap() -> None:
    assert not TimeWindow(_dt(18), _dt(19)).overlaps(TimeWindow(_dt(20), _dt(21)))


def test_gap_minutes_before() -> None:
    previous = TimeWindow(_dt(18), _dt(19))
    assert previous.gap_minutes_before(TimeWindow(_dt(20), _dt(21))) == 60
    assert previous.gap_minutes_before(TimeWindow(_dt(18, 30), _dt(19, 30))) == -30
