from __future__ import annotations

from datetime import UTC, date, datetime, time

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


def test_from_schedule_builds_window_and_normalizes_to_utc() -> None:
    window = TimeWindow.from_schedule(date(2026, 12, 24), time(20, 0), 60)
    assert window.start == datetime(2026, 12, 24, 20, 0, tzinfo=UTC)
    assert window.end == datetime(2026, 12, 24, 21, 0, tzinfo=UTC)
    assert window.duration_minutes == 60


def test_from_schedule_rejects_non_positive_duration() -> None:
    with pytest.raises(ValueError):
        TimeWindow.from_schedule(date(2026, 12, 24), time(20, 0), 0)


def test_from_event_projects_midnight_crossing() -> None:
    window = TimeWindow.from_event(date(2026, 12, 24), time(23, 0), time(0, 30))
    assert window.start == datetime(2026, 12, 24, 23, 0, tzinfo=UTC)
    assert window.end == datetime(2026, 12, 25, 0, 30, tzinfo=UTC)


def test_from_event_rejects_empty_window() -> None:
    with pytest.raises(ValueError):
        TimeWindow.from_event(date(2026, 12, 24), time(20, 0), time(20, 0))
