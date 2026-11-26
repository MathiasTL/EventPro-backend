"""Construcción compartida del evento y sus reservas de inventario.

La usan el flujo manual y la verificación de adelantos conversacionales para que ambos
produzcan el mismo evento ``AWAITING_SIGNATURE`` a partir de los importes de la cotización.
"""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.catalog_dto import InventoryRequirementDTO
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)


async def add_event_with_reservations(
    session: AsyncSession,
    *,
    event_id: UUID,
    quote_id: UUID,
    event_date: date,
    start_time: time,
    address: str,
    district: str,
    total_amount: Decimal,
    mobility_amount: Decimal,
    advance_amount: Decimal,
    observations: str | None,
    window: TimeWindow,
    requirements: tuple[InventoryRequirementDTO, ...],
) -> None:
    session.add(
        EventModel(
            id=event_id,
            event_code="EVT-" + event_id.hex[:20].upper(),
            quote_id=quote_id,
            event_date=event_date,
            start_time=start_time,
            end_time=window.end.time(),
            address=address,
            district=district,
            total_services_amount=total_amount - mobility_amount,
            total_mobility_amount=mobility_amount,
            final_total_amount=total_amount,
            advance_paid=advance_amount,
            status="AWAITING_SIGNATURE",
            client_observations=observations,
        )
    )
    await session.flush()
    for requirement in requirements:
        session.add(
            InventoryReservationModel(
                event_id=event_id,
                inventory_item_id=requirement.inventory_item_id,
                quantity=requirement.quantity,
                starts_at=window.start,
                ends_at=window.end,
            )
        )
