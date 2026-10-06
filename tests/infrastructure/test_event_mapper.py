from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import (
    event_to_domain,
    event_to_model,
)
from tests.event_support import make_event


def test_event_round_trip_preserves_all_fields_and_exact_amounts() -> None:
    event = make_event(client_observations="  No reggaetón.\nGorila al min 45. ")
    row = event_to_model(event)
    assert row.advance_paid == event.advance_paid.amount
    assert row.status == event.status.value
    assert event_to_domain(row) == event
