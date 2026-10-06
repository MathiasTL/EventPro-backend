"""Conversión explícita entre ORM y agregado; ninguna entidad importa SQLAlchemy."""

from app.domain.entities.event import Event
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel


def event_to_domain(row: EventModel) -> Event:
    return Event(
        id=row.id,
        event_code=row.event_code,
        quote_id=row.quote_id,
        event_date=row.event_date,
        start_time=row.start_time,
        end_time=row.end_time,
        address=row.address,
        district=row.district,
        client_observations=row.client_observations,
        status=EventStatus(row.status),
        total_services_amount=Money(row.total_services_amount),
        total_mobility_amount=Money(row.total_mobility_amount),
        final_total_amount=Money(row.final_total_amount),
        advance_paid=Money(row.advance_paid),
        pre_show_balance_paid=Money(row.pre_show_balance_paid),
        extra_hours_amount=Money(row.extra_hours_amount),
        created_at=row.created_at,
    )


def event_to_model(event: Event) -> EventModel:
    return EventModel(
        id=event.id,
        event_code=event.event_code,
        quote_id=event.quote_id,
        event_date=event.event_date,
        start_time=event.start_time,
        end_time=event.end_time,
        address=event.address,
        district=event.district,
        client_observations=event.client_observations,
        status=event.status.value,
        total_services_amount=event.total_services_amount.amount,
        total_mobility_amount=event.total_mobility_amount.amount,
        final_total_amount=event.final_total_amount.amount,
        advance_paid=event.advance_paid.amount,
        pre_show_balance_paid=event.pre_show_balance_paid.amount,
        extra_hours_amount=event.extra_hours_amount.amount,
        created_at=event.created_at,
    )
