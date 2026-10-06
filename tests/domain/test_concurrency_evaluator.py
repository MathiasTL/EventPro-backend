from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.services.concurrency_evaluator import ConcurrencyEvaluator
from app.domain.value_objects.time_window import TimeWindow

_BASE = datetime(2026, 10, 5, 18, 0)


def _window(start_minutes: int, duration_minutes: int) -> TimeWindow:
    start = _BASE + timedelta(minutes=start_minutes)
    return TimeWindow(start, start + timedelta(minutes=duration_minutes))


def test_default_threshold() -> None:
    assert ConcurrencyEvaluator().threshold == 3


def test_negative_threshold_rejected() -> None:
    with pytest.raises(ValueError):
        ConcurrencyEvaluator(threshold=-1)


def test_candidate_is_counted() -> None:
    evaluator = ConcurrencyEvaluator(threshold=3)
    candidate = _window(0, 60)
    assert evaluator.simultaneous_count([], candidate) == 1
    assert not evaluator.requires_manual_approval([], candidate)


def test_three_overlaps_are_automatic() -> None:
    evaluator = ConcurrencyEvaluator(threshold=3)
    existing = [_window(0, 60), _window(10, 60), _window(20, 60)]
    candidate = _window(30, 60)
    # 3 existentes + el nuevo = 4 -> supera el umbral de 3.
    assert evaluator.simultaneous_count(existing, candidate) == 4
    assert evaluator.requires_manual_approval(existing, candidate)


def test_two_overlaps_plus_candidate_equal_three_is_automatic() -> None:
    evaluator = ConcurrencyEvaluator(threshold=3)
    existing = [_window(0, 60), _window(10, 60)]
    candidate = _window(20, 60)
    assert evaluator.simultaneous_count(existing, candidate) == 3
    assert not evaluator.requires_manual_approval(existing, candidate)


def test_adjacent_windows_do_not_count_for_threshold() -> None:
    evaluator = ConcurrencyEvaluator(threshold=3)
    # Tres eventos contiguos que terminan exactamente cuando empieza el siguiente.
    existing = [_window(0, 60), _window(60, 60), _window(120, 60)]
    candidate = _window(180, 60)
    assert evaluator.simultaneous_count(existing, candidate) == 1
    assert not evaluator.requires_manual_approval(existing, candidate)


def test_custom_threshold() -> None:
    evaluator = ConcurrencyEvaluator(threshold=1)
    existing = [_window(0, 60)]
    assert evaluator.requires_manual_approval(existing, _window(10, 60))
