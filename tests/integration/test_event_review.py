"""Regresiones US-18 contra PostgreSQL real y ocupación del baseline."""

import asyncio
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.use_cases.event.register_event_extension import RegisterEventExtensionUseCase
from app.domain.exceptions.event_exceptions import EventResourceConflictError
from app.domain.value_objects.event_status import EventStatus
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from tests.event_support import make_event
from tests.extension_support import extension_input
from tests.integration._support import insert_quotes, run_migrations
from tests.integration.test_event_extensions import (
    SqlAlchemyEventRepository,
    seed_event,
    storage_at,
)
from tests.start_event_support import FixedClock

pytestmark = pytest.mark.integration


async def add_other(factory, original, **changes):
    other = make_event(event_date=original.event_date, **changes)
    await insert_quotes(factory.kw["bind"], [other.quote_id])
    async with factory() as session:
        session.add(event_to_model(other))
        await session.commit()
    return other


async def add_reservations(factory, event, other=None, stock=1, other_status="ACTIVE"):
    start = datetime.combine(event.event_date, time(21, 10), UTC)
    end = datetime.combine(event.event_date, time(22, 50), UTC)
    async with factory() as session:
        item = await session.scalar(
            text(
                "INSERT INTO inventory_items (name, service_category, total_stock) "
                "VALUES (:name, 'DECORATION', :stock) RETURNING id"
            ),
            {"name": str(uuid4()), "stock": stock},
        )
        own = InventoryReservationModel(
            event_id=event.id,
            inventory_item_id=item,
            quantity=1,
            starts_at=start,
            ends_at=end,
        )
        session.add(own)
        if other is not None:
            session.add(
                InventoryReservationModel(
                    event_id=other.id,
                    inventory_item_id=item,
                    quantity=1,
                    starts_at=end + timedelta(minutes=10),
                    ends_at=end + timedelta(hours=1),
                    status=other_status,
                )
            )
        await session.commit()
        return own.id, start, end


@pytest.mark.parametrize(
    "resource", ["stock", "crew", "transit-unknown", "transit-long", "threshold", "extended-crew"]
)
def test_real_conflicts_leave_no_partial_writes(database_url, tmp_path, resource):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        storage = storage_at(tmp_path)
        try:
            event, actor = await seed_event(factory)
            changes = dict(start_time=time(23, 15), end_time=time(23, 45))
            if resource in {"crew", "threshold"}:
                changes = dict(start_time=time(22, 45), end_time=time(23, 45))
            elif resource == "extended-crew":
                changes = dict(start_time=time(19), end_time=time(20), extra_minutes_total=180)
            other = await add_other(factory, event, **changes)
            reservation_id = None
            if resource == "stock":
                reservation_id, _, old_end = await add_reservations(factory, event, other)
            if resource in {"crew", "transit-unknown", "transit-long", "extended-crew"}:
                async with factory() as session:
                    crew = await session.scalar(
                        text(
                            "INSERT INTO crews (leader_name, phone, service_category) "
                            "VALUES ('Test', '123', 'SHOW') RETURNING id"
                        )
                    )
                    for row in (event, other):
                        await session.execute(
                            text(
                                "INSERT INTO crew_assignments "
                                "(event_id, crew_id, transit_interval_minutes) "
                                "VALUES (:event, :crew, :interval)"
                            ),
                            {
                                "event": row.id,
                                "crew": crew,
                                "interval": 30 if resource == "transit-long" else None,
                            },
                        )
                    await session.commit()
            async with factory() as session:
                with pytest.raises(EventResourceConflictError):
                    await RegisterEventExtensionUseCase(
                        SqlAlchemyEventRepository(session),
                        storage,
                        FakeCrewScheduleReadAdapter(),
                        FixedClock(),
                        simultaneous_threshold=1 if resource == "threshold" else 3,
                    ).execute(extension_input(event.id), actor)
                assert not session.in_transaction()
            assert list((tmp_path / "evidence").iterdir()) == []
            async with factory() as session:
                row = await session.get(EventModel, event.id)
                assert row.extra_minutes_total == 0
                assert row.status == "IN_PROGRESS"
                assert await session.scalar(select(func.count()).select_from(PaymentModel)) == 0
                if reservation_id:
                    assert (
                        await session.get(InventoryReservationModel, reservation_id)
                    ).ends_at == old_end
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize("commit_failure", [False, True])
def test_reservation_margins_extend_atomically_and_totals_use_one_query(
    database_url, tmp_path, commit_failure
):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            event, actor = await seed_event(factory)
            other = await add_other(factory, event, status=EventStatus.CANCELLED)
            own_id, start, end = await add_reservations(
                factory, event, other, other_status="RELEASED"
            )
            async with factory() as session:
                repo = SqlAlchemyEventRepository(session)

                def reject(_session):
                    raise RuntimeError("rollback reservation")

                if commit_failure:
                    sqlalchemy_event.listen(session.sync_session, "before_commit", reject)
                use_case = RegisterEventExtensionUseCase(
                    repo, storage_at(tmp_path), FakeCrewScheduleReadAdapter(), FixedClock()
                )
                if commit_failure:
                    with pytest.raises(RuntimeError, match="rollback reservation"):
                        await use_case.execute(extension_input(event.id), actor)
                else:
                    await use_case.execute(extension_input(event.id), actor)
                    await use_case.execute(
                        extension_input(event.id, extra_minutes=60, agreed_rate=Decimal("50")),
                        actor,
                    )
            async with factory() as session:
                row = await session.get(InventoryReservationModel, own_id)
                assert row.starts_at == start
                assert row.ends_at == end + timedelta(minutes=0 if commit_failure else 90)
                statements = []

                def observe(_conn, _cursor, statement, _parameters, _context, _many):
                    statements.append(statement)

                sqlalchemy_event.listen(engine.sync_engine, "before_cursor_execute", observe)
                totals = await SqlAlchemyEventRepository(session).get_verified_extension_totals(
                    event.id
                )
                sqlalchemy_event.remove(engine.sync_engine, "before_cursor_execute", observe)
                assert len(statements) == 1
                assert totals.extra_minutes == (0 if commit_failure else 90)
                assert totals.amount.amount == (0 if commit_failure else Decimal("150"))
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize("resource", ["stock", "threshold"])
def test_distinct_events_share_transactional_availability_lock(database_url, tmp_path, resource):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        locked, waiting, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        tasks = []
        try:
            first, actor = await seed_event(factory)
            second = await add_other(
                factory,
                first,
                status=EventStatus.IN_PROGRESS,
                **(
                    dict(start_time=time(23), end_time=time(23, 30))
                    if resource == "threshold"
                    else {}
                ),
            )
            if resource == "threshold":
                next_day = make_event(
                    event_date=first.event_date + timedelta(days=1),
                    start_time=time(0),
                    end_time=time(0, 45),
                )
                await insert_quotes(engine, [next_day.quote_id])
                async with factory() as session:
                    session.add(event_to_model(next_day))
                    await session.commit()
            own_id, _, _ = await add_reservations(factory, first, second, stock=2)

            class BlockingRepository(SqlAlchemyEventRepository):
                async def get_by_id_for_update(self, event_id):
                    found = await super().get_by_id_for_update(event_id)
                    locked.set()
                    await release.wait()
                    return found

            def observe(_conn, _cursor, statement, _parameters, _context, _many):
                if (
                    len(tasks) == 2
                    and asyncio.current_task() is tasks[1]
                    and "pg_advisory_xact_lock" in statement
                ):
                    waiting.set()

            async def extend(row, blocked):
                async with factory() as session:
                    repo = (
                        BlockingRepository(session)
                        if blocked
                        else SqlAlchemyEventRepository(session)
                    )
                    return await RegisterEventExtensionUseCase(
                        repo,
                        storage_at(tmp_path),
                        FakeCrewScheduleReadAdapter(),
                        FixedClock(),
                        simultaneous_threshold=2 if resource == "threshold" else 3,
                    ).execute(
                        extension_input(
                            row.id, extra_minutes=60 if resource == "threshold" else 30
                        ),
                        actor,
                    )

            sqlalchemy_event.listen(engine.sync_engine, "before_cursor_execute", observe)
            tasks.append(asyncio.create_task(extend(first, True)))
            await asyncio.wait_for(locked.wait(), 5)
            tasks.append(asyncio.create_task(extend(second, False)))
            await asyncio.wait_for(waiting.wait(), 5)
            assert not tasks[1].done()
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
            assert not isinstance(results[0], BaseException)
            if resource == "threshold":
                assert isinstance(results[1], EventResourceConflictError)
                assert "aprobación manual" in str(results[1])
                assert len(list((tmp_path / "evidence").iterdir())) == 1
            else:
                assert not isinstance(results[1], BaseException)
            async with factory() as session:
                assert (await session.get(EventModel, first.id)).extra_minutes_total == (
                    60 if resource == "threshold" else 30
                )
                assert (await session.get(EventModel, second.id)).extra_minutes_total == (
                    0 if resource == "threshold" else 30
                )
                assert (await session.get(InventoryReservationModel, own_id)).ends_at.time() == (
                    time(23, 50) if resource == "threshold" else time(23, 20)
                )
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await engine.dispose()

    asyncio.run(exercise())
