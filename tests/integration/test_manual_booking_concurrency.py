"""Interoperabilidad con otro escritor de ocupación y un pool de una conexión."""

import asyncio
from datetime import date, time
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence.database import get_session
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_occupancy,
)

from .test_manual_booking_flow import confirm, register
from .test_manual_booking_flow import scenario as scenario_fixture

scenario = scenario_fixture


async def test_common_lock_serializes_manual_flow_with_another_occupancy_writer(scenario):
    client, factory, payload, headers, _ = scenario
    other = {**payload, "quote_id": str(uuid4()), "phone": f"9{uuid4().int % 10**8:08d}"}
    for incoming in [payload, other]:
        assert (await register(client, incoming, headers["SUPERADMIN"])).status_code == 201
    event_id = uuid4()
    window = TimeWindow.from_schedule(date.fromisoformat(payload["event_date"]), time(23, 30), 90)
    async with factory() as writer:
        await sqlalchemy_event_occupancy.SqlAlchemyEventOccupancy(writer).lock_availability()
        task = asyncio.create_task(confirm(client, payload, headers["ENCARGADO"]))
        await asyncio.sleep(0.1)
        assert not task.done(), "La reserva manual debe esperar al escritor existente"
        writer.add(
            EventModel(
                id=event_id,
                event_code=f"OTHER-{event_id.hex[:20]}",
                quote_id=other["quote_id"],
                event_date=window.start.date(),
                start_time=window.start.time().replace(tzinfo=None),
                end_time=window.end.time(),
                address="Av. Principal",
                district="Lima",
                status="AWAITING_SIGNATURE",
                total_services_amount=100,
                total_mobility_amount=0,
                final_total_amount=100,
                advance_paid=10,
            )
        )
        await writer.flush()
        item = await writer.scalar(
            text("SELECT inventory_item_id FROM package_inventory_items WHERE package_id=:id"),
            {"id": payload["package_id"]},
        )
        writer.add(
            InventoryReservationModel(
                event_id=event_id,
                inventory_item_id=item,
                quantity=1,
                starts_at=window.start,
                ends_at=window.end,
            )
        )
        await writer.commit()
    result = await asyncio.wait_for(task, timeout=15)
    assert result.status_code == 200, result.text
    assert result.json()["payment_status"] == "REQUIRES_MANUAL_APPROVAL"
    assert result.json()["event_id"] is None


async def test_same_session_allows_confirmation_with_a_one_connection_pool(scenario):
    client, _, payload, headers, _ = scenario
    engine = create_async_engine(
        get_settings().database_url, pool_size=1, max_overflow=0, pool_timeout=3
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sessions = []

    async def one_session():
        async with factory() as session:
            sessions.append(session)
            yield session

    client._transport.app.dependency_overrides[get_session] = one_session
    try:
        assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
        sessions.clear()
        result = await asyncio.wait_for(confirm(client, payload, headers["ENCARGADO"]), timeout=10)
        assert result.status_code == 200, result.text
        assert len(sessions) == 1
    finally:
        await engine.dispose()
