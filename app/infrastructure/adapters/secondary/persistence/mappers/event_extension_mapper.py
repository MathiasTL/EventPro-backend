from app.domain.entities.event_extension import EventExtension
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.models.event_extension_model import (
    EventExtensionModel,
)


def extension_to_domain(row: EventExtensionModel) -> EventExtension:
    return EventExtension(
        id=row.id,
        event_id=row.event_id,
        payment_id=row.payment_id,
        extra_minutes=row.extra_minutes,
        agreed_rate=Money(row.agreed_rate),
        requested_at=row.requested_at,
    )


def extension_to_model(entity: EventExtension) -> EventExtensionModel:
    return EventExtensionModel(
        id=entity.id,
        event_id=entity.event_id,
        payment_id=entity.payment_id,
        extra_minutes=entity.extra_minutes,
        agreed_rate=entity.agreed_rate.amount,
        requested_at=entity.requested_at,
    )
