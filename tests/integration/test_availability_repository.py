"""Prueba de integración del repositorio de disponibilidad (Testcontainers).

Marcada como ``integration``; correr con ``pytest -m integration``. Verifica las
consultas de inventario, reservas activas y eventos que cuentan para el umbral.
"""

from __future__ import annotations

import asyncio
from datetime import date, time
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence import (
    SqlAlchemyAvailabilityRepository,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.models.availability_models import (
    InventoryReservationModel,
)
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    InventoryItemModel,
    PackageInventoryItemModel,
    PackageModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel

from ._support import run_migrations

pytestmark = pytest.mark.integration

_DAY = date(2026, 12, 24)


async def _create_event(session: AsyncSession, code: str, start: time, end: time, status: str):
    event = EventModel(
        id=uuid4(),
        event_code=code,
        quote_id=uuid4(),
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

    async def _exercise() -> tuple[bool, bool, bool, bool]:
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

                # Solapa, contiguo, cancelado y cruzando medianoche.
                overlapping = await _create_event(
                    session, "EVT-2026-0001", time(19, 0), time(21, 0)
                )
                adjacent = await _create_event(session, "EVT-2026-0002", time(21, 0), time(22, 0))
                cancelled = await _create_event(
                    session, "EVT-2026-0003", time(19, 30), time(20, 30), status="CANCELLED"
                )
                crossing = await _create_event(session, "EVT-2026-0004", time(23, 0), time(0, 30))

                for event, quantity, status in (
                    (overlapping, 2, "ACTIVE"),
                    (overlapping, 9, "RELEASED"),
                    (crossing, 5, "ACTIVE"),
                ):
                    session.add(
                        InventoryReservationModel(
                            id=uuid4(),
                            event_id=event.id,
                            inventory_item_id=item.id,
                            quantity=quantity,
                            starts_at=TimeWindow.from_schedule(_DAY, time(19, 0), 180).start,
                            ends_at=TimeWindow.from_schedule(_DAY, time(19, 0), 180).end,
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
                # ni la que está fuera de la ventana).
                only_active_overlap = (
                    len(reservations) == 1
                    and reservations[0].quantity == 2
                    and reservations[0].event_id == overlapping.id
                )

                countable = await repository.list_countable_events(window)
                only_overlapping_counted = [row.event_id for row in countable] == [overlapping.id]

                empty = await repository.get_package_inventory_requirements(uuid4())
                no_requirements = empty == ()
                _ = (adjacent, cancelled)  # solo para dejar explícitos los casos
                return (
                    has_requirement,
                    only_active_overlap,
                    only_overlapping_counted,
                    no_requirements,
                )
        finally:
            await engine.dispose()

    has_requirement, only_active_overlap, only_overlapping_counted, no_requirements = asyncio.run(
        _exercise()
    )
    assert has_requirement
    assert only_active_overlap
    assert only_overlapping_counted
    assert no_requirements
