"""Conversión explícita entre ORM y el agregado Quote; la entidad no importa SQLAlchemy."""

from app.domain.entities.quote import Quote, QuoteExtraLine, QuoteSource, QuoteStatus
from app.domain.value_objects.liquidation import Liquidation
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.secondary.persistence.models.quote_model import (
    QuoteExtraModel,
    QuoteModel,
)


def quote_to_domain(row: QuoteModel) -> Quote:
    """Reconstruye el agregado sin recalcular: se respeta lo persistido (también filas heredadas).

    El balance se divide en servicios y movilidad solo informativamente; las filas del flujo
    manual heredado pueden traer ``pending_balance`` sin movilidad y no se reinterpretan.
    """

    total = Money(row.total_amount)
    advance = Money(row.advance_amount)
    services = Money(row.services_subtotal)
    mobility = Money(row.final_mobility_amount)
    liquidation = Liquidation(
        services_subtotal=services,
        mobility_amount=mobility,
        total_amount=total,
        advance_amount=advance,
        pending_balance=Money(row.pending_balance),
        balance_services=services - advance,
        balance_mobility=mobility,
    )
    return Quote(
        id=row.id,
        client_id=row.client_id,
        source=QuoteSource(row.source),
        event_date=row.event_date,
        event_time=row.event_time,
        location_address=row.location_address,
        location_district=row.location_district,
        latitude=row.latitude,
        longitude=row.longitude,
        package_id=row.package_id,
        theme_id=row.theme_id,
        client_provides_mobility=row.client_provides_mobility,
        calculated_distance_km=row.calculated_distance_km,
        calculated_transit_minutes=row.calculated_transit_minutes,
        base_mobility_amount=Money(row.base_mobility_amount),
        mobility_overridden=row.mobility_overridden,
        mobility_override_reason=row.mobility_override_reason,
        liquidation=liquidation,
        extras=tuple(
            QuoteExtraLine(
                extra_id=extra.extra_id,
                quantity=extra.quantity,
                unit_price=Money(extra.unit_price),
                subtotal=Money(extra.subtotal),
            )
            for extra in row.extras
        ),
        status=QuoteStatus(row.status),
        sent_at=row.sent_at,
        expires_at=row.expires_at,
        manual_request_hash=row.manual_request_hash,
        created_at=row.created_at,
    )


def apply_quote_to_model(row: QuoteModel, entity: Quote) -> None:
    """Copia los campos escalares del agregado a la fila (los extras son inmutables)."""

    row.client_id = entity.client_id
    row.source = entity.source.value
    row.event_date = entity.event_date
    row.event_time = entity.event_time
    row.location_address = entity.location_address
    row.location_district = entity.location_district
    row.latitude = entity.latitude
    row.longitude = entity.longitude
    row.package_id = entity.package_id
    row.theme_id = entity.theme_id
    row.client_provides_mobility = entity.client_provides_mobility
    row.calculated_distance_km = entity.calculated_distance_km
    row.calculated_transit_minutes = entity.calculated_transit_minutes
    row.base_mobility_amount = entity.base_mobility_amount.amount
    row.final_mobility_amount = entity.liquidation.mobility_amount.amount
    row.mobility_overridden = entity.mobility_overridden
    row.mobility_override_reason = entity.mobility_override_reason
    row.services_subtotal = entity.liquidation.services_subtotal.amount
    row.total_amount = entity.liquidation.total_amount.amount
    row.advance_amount = entity.liquidation.advance_amount.amount
    row.pending_balance = entity.liquidation.pending_balance.amount
    row.status = entity.status.value
    row.sent_at = entity.sent_at
    row.expires_at = entity.expires_at
    row.manual_request_hash = entity.manual_request_hash


def quote_to_model(entity: Quote) -> QuoteModel:
    row = QuoteModel(id=entity.id, created_at=entity.created_at)
    apply_quote_to_model(row, entity)
    row.extras = [
        QuoteExtraModel(
            quote_id=entity.id,
            extra_id=line.extra_id,
            quantity=line.quantity,
            unit_price=line.unit_price.amount,
            subtotal=line.subtotal.amount,
        )
        for line in entity.extras
    ]
    return row
