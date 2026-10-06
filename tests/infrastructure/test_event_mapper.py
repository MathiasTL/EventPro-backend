from datetime import UTC, datetime

from app.domain.value_objects.event_status import EventStatus
from app.infrastructure.adapters.secondary.external_services.system_clock_adapter import (
    SystemClockAdapter,
)
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import (
    event_to_domain,
    event_to_model,
)
from tests.event_support import make_event
from tests.start_event_support import STARTED_AT


def test_event_round_trip_preserves_all_fields_and_exact_amounts() -> None:
    event = make_event(client_observations="  No reggaetón.\nGorila al min 45. ")
    row = event_to_model(event)
    assert row.advance_paid == event.advance_paid.amount
    assert row.status == event.status.value
    assert event_to_domain(row) == event


def test_started_event_round_trip_preserves_actual_instant() -> None:
    event = make_event(status=EventStatus.IN_PROGRESS, actual_start_time=STARTED_AT)
    row = event_to_model(event)
    assert row.actual_start_time == STARTED_AT
    assert event_to_domain(row) == event


def test_system_clock_is_aware_utc() -> None:
    before = datetime.now(UTC)
    actual = SystemClockAdapter().utcnow()
    assert before <= actual <= datetime.now(UTC)
    assert actual.tzinfo is UTC
