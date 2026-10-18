from datetime import timedelta

import pytest

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_SCHEDULE,
    RetrySchedule,
)


@pytest.mark.parametrize(
    ("failed_attempts", "expected"),
    [
        (1, timedelta(seconds=30)),
        (2, timedelta(minutes=2)),
        (3, timedelta(minutes=10)),
        (4, timedelta(minutes=30)),
        (5, timedelta(hours=2)),
    ],
)
def test_default_schedule_matches_rnf_03_2(failed_attempts: int, expected: timedelta) -> None:
    assert DEFAULT_RETRY_SCHEDULE.delay_after(failed_attempts) == expected


def test_delay_after_repeats_the_last_delay_when_attempts_exceed_the_schedule() -> None:
    assert DEFAULT_RETRY_SCHEDULE.delay_after(9) == timedelta(hours=2)


@pytest.mark.parametrize("invalid", [0, -1, True, "1", 1.5])
def test_delay_after_rejects_invalid_attempt_numbers(invalid: object) -> None:
    with pytest.raises(ValidationError):
        DEFAULT_RETRY_SCHEDULE.delay_after(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize("delays", [(), (timedelta(0),), (timedelta(seconds=-5),)])
def test_schedule_rejects_empty_or_non_positive_delays(delays: tuple[timedelta, ...]) -> None:
    with pytest.raises(ValidationError):
        RetrySchedule(delays)


def test_default_max_attempts_is_six() -> None:
    # RNF-03.2: cinco reintentos más el primer envío.
    assert DEFAULT_MAX_ATTEMPTS == 6
