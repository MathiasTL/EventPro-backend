from app.domain.value_objects.event_status import EventStatus
from app.infrastructure.adapters.secondary.persistence.mappers.event_extension_mapper import (
    extension_to_domain,
    extension_to_model,
)
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import (
    event_to_domain,
    event_to_model,
)
from tests.domain.test_event_extensions import extend
from tests.event_support import make_event


def test_extension_and_event_roundtrip_preserves_minutes_money_and_date():
    event = make_event(status=EventStatus.IN_PROGRESS)
    extension = extend(event, 60, "123.45")
    assert extension_to_domain(extension_to_model(extension)) == extension
    assert event_to_domain(event_to_model(event)) == event
