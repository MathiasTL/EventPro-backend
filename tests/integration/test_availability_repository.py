"""Prueba de integración del repositorio de disponibilidad (Testcontainers).

Marcada como ``integration``; correr con ``pytest -m integration``. Verifica las
consultas de inventario, reservas activas y eventos que cuentan para el umbral.

``events.quote_id`` es clave foránea y única hacia ``quotes``; como el modelo ORM de
cotizaciones aún no existe (E1), las filas de ``clients`` y ``quotes`` se insertan con
SQL directo.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence import (
    SqlAlchemyAvailabilityRepository,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    InventoryItemModel,
    PackageInventoryItemModel,
    PackageModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)

from ._support import run_migrations

pytestmark = pytest.mark.integration

_DAY = date(2026, 12, 24)
_SENT_AT = datetime(2026, 12, 24, 10, 0, tzinfo=UTC)
_EXPIRES_AT = datetime(2026, 12, 25, 10, 0, tzinfo=UTC)

_INSERT_CLIENT = text("INSERT INTO clients (id, phone, full_name) VALUES (:id, :phone, :full_name)")
_INSERT_QUOTE = text(
    """
    INSERT INTO quotes (
        id, client_id, source, event_date, event_time, location_address,
        location_district, package_id, services_subtotal, total_amount,
        advance_amount, pending_balance, status, sent_at, expires_at
    ) VALUES (
        :id, :client_id, 'WHATSAPP', :event_date, :event_time, :address,
        :district, :package_id, 1000.00, 1000.00, 100.00, 900.00, 'SENT',
        :sent_at, :expires_at
    )
    """
)


async def _new_quote(
    session: AsyncSession, *, client_id: UUID, package_id: UUID, event_time: time
) -> UUID:
    quote_id = uuid4()
    await session.execute(
        _INSERT_QUOTE,
        {
            "id": quote_id,
            "client_id": client_id,
            "event_date": _DAY,
            "event_time": event_time,
            "address": "Av. Primavera 123",
            "district": "San Borja",
            "package_id": package_id,
            "sent_at": _SENT_AT,
            "expires_at": _EXPIRES_AT,
        },
    )
    return quote_id


async def _create_event(
    session: AsyncSession,
    code: str,
    start: time,
    end: time,
    *,
    quote_id: UUID,
    status: str = "SCHEDULED",
) -> EventModel:
    event = EventModel(
        id=uuid4(),
        event_code=code,
        quote_id=quote_id,
        event_date=_DAY,
        start_time=start,
        end_time=end,
        address="Av. Primavera 123",
        district="San Borja",
        client_observations=None,
        status=status,
        total_services_amount=Decimal("1000.00"),
        total_mobility_amount=Decimal("0.00"),
        final_total_amount=Decimal("1000.00"),
    )
    session.add(event)
    await session.flush()
    return event


def test_availability_repository_queries(database_url: str) -> None:
    run_migrations(database_url)

    async def _exercise() -> tuple[bool, bool, bool, bool, bool]:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                item = InventoryItemModel(
                    id=uuid4(),
                    name="Toldo Estándar 3x3 m",
                    service_category="TENTS",
                    total_stock=10,
                    is_active=True,
                )
                package = PackageModel(
                    id=uuid4(),
                    name="Ambientación y Toldos Estándar",
                    service_category="TENTS",
                    base_price=Decimal("900.00"),
                    direct_cost=Decimal("450.00"),
                    duration_minutes=480,
                    is_active=True,
                )
                session.add_all([item, package])
                await session.flush()
                session.add(
                    PackageInventoryItemModel(
                        id=uuid4(),
                        package_id=package.id,
                        inventory_item_id=item.id,
                        quantity=1,
                    )
                )

                client_id = uuid4()
                await session.execute(
                    _INSERT_CLIENT,
                    {"id": client_id, "phone": "+51999000111", "full_name": "Cliente Prueba"},
                )

                # Solapa, contiguo, cancelado y cruzando medianoche. Cada evento
                # requiere su propia cotización (quote_id es FK y único).
                overlapping = await _create_event(
                    session,
                    "EVT-2026-0001",
                    time(19, 0),
                    time(21, 0),
                    quote_id=await _new_quote(
                        session, client_id=client_id, package_id=package.id, event_time=time(19, 0)
                    ),
                )
                adjacent = await _create_event(
                    session,
                    "EVT-2026-0002",
                    time(21, 0),
                    time(22, 0),
                    quote_id=await _new_quote(
                        session, client_id=client_id, package_id=package.id, event_time=time(21, 0)
                    ),
                )
                cancelled = await _create_event(
                    session,
                    "EVT-2026-0003",
                    time(19, 30),
                    time(20, 30),
                    quote_id=await _new_quote(
                        session,
                        client_id=client_id,
                        package_id=package.id,
                        event_time=time(19, 30),
                    ),
                    status="CANCELLED",
                )
                crossing = await _create_event(
                    session,
                    "EVT-2026-0004",
                    time(23, 0),
                    time(0, 30),
                    quote_id=await _new_quote(
                        session, client_id=client_id, package_id=package.id, event_time=time(23, 0)
                    ),
                )

                # Reservas en la ventana real de cada evento: la de ``overlapping``
                # solapa con la consulta; la de ``crossing`` (23:00–00:30) no.
                for event, quantity, status in (
                    (overlapping, 2, "ACTIVE"),
                    (overlapping, 9, "RELEASED"),
                    (crossing, 5, "ACTIVE"),
                ):
                    event_window = TimeWindow.from_event(
                        event.event_date, event.start_time, event.end_time
                    )
                    session.add(
                        InventoryReservationModel(
                            id=uuid4(),
                            event_id=event.id,
                            inventory_item_id=item.id,
                            quantity=quantity,
                            starts_at=event_window.start,
                            ends_at=event_window.end,
                            status=status,
                        )
                    )
                await session.commit()

                repository = SqlAlchemyAvailabilityRepository(session)
                window = TimeWindow.from_schedule(_DAY, time(20, 0), 60)

                requirements = await repository.get_package_inventory_requirements(package.id)
                has_requirement = (
                    len(requirements) == 1
                    and requirements[0].inventory_item_id == item.id
                    and requirements[0].quantity == 1
                    and requirements[0].total_stock == 10
                )

                reservations = await repository.list_active_reservations([item.id], window)
                # Solo debe devolver la reserva ACTIVA que solapa (no la RELEASED
                # ni la del evento que cruza la medianoche).
                only_active_overlap = (
                    len(reservations) == 1
                    and reservations[0].quantity == 2
                    and reservations[0].event_id == overlapping.id
                )

                countable = await repository.list_countable_events(window)
                countable_ids = [row.event_id for row in countable]
                only_overlapping_counted = countable_ids == [overlapping.id]
                excluded_from_threshold = (
                    adjacent.id not in countable_ids
                    and cancelled.id not in countable_ids
                    and crossing.id not in countable_ids
                )

                empty = await repository.get_package_inventory_requirements(uuid4())
                no_requirements = empty == ()
                return (
                    has_requirement,
                    only_active_overlap,
                    only_overlapping_counted,
                    excluded_from_threshold,
                    no_requirements,
                )
        finally:
            await engine.dispose()

    (
        has_requirement,
        only_active_overlap,
        only_overlapping_counted,
        excluded_from_threshold,
        no_requirements,
    ) = asyncio.run(_exercise())
    assert has_requirement
    assert only_active_overlap
    assert only_overlapping_counted
    assert excluded_from_threshold
    assert no_requirements
