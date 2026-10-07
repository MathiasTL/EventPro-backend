"""Columna de inicio real, endpoint real, rollback e inicios concurrentes."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.use_cases.event.start_event import StartEventUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.exceptions.event_exceptions import InvalidEventStateError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine, get_session
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_repository,
)
from app.infrastructure.adapters.secondary.persistence.user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.di import containers
from app.infrastructure.di.containers import (
    get_clock_port,
    get_crew_schedule_read_port,
    get_pre_show_payment_verification_port,
)
from app.main import create_app
from tests.event_support import make_event
from tests.start_event_support import STARTED_AT, FixedClock, RecordingPayments

from ._support import insert_quotes, insert_user, run_migrations

pytestmark = pytest.mark.integration


def test_actual_start_time_column_is_nullable_utc_without_default(database_url: str) -> None:
    run_migrations(database_url)
    event_id = uuid4()
    quote_id = uuid4()

    async def exercise() -> None:
        engine = build_engine(database_url)
        try:
            await insert_quotes(engine, [quote_id])
            async with engine.begin() as connection:
                columns = await connection.run_sync(
                    lambda conn: inspect(conn).get_columns("events")
                )
                actual = [column for column in columns if column["name"] == "actual_start_time"]
                assert len(actual) == 1
                assert actual[0]["nullable"] is True
                assert actual[0]["default"] is None
                assert actual[0]["type"].timezone is True
                await connection.execute(
                    text(
                        "INSERT INTO events (id, event_code, quote_id, event_date, "
                        "start_time, end_time, "
                        "address, district, status, total_services_amount, total_mobility_amount, "
                        "final_total_amount) VALUES (:id, 'EVT-LEGACY', :quote_id, "
                        "'2026-10-15', '21:30', '22:30', 'Local', 'Miraflores', "
                        "'IN_PROGRESS', 980, 100.50, 1080.50)"
                    ),
                    {"id": event_id, "quote_id": quote_id},
                )
                assert (
                    await connection.scalar(
                        text("SELECT actual_start_time FROM events WHERE id = :id"),
                        {"id": event_id},
                    )
                    is None
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_start_api_persists_state_balance_and_utc(database_url: str) -> None:
    run_migrations(database_url)

    async def exercise() -> None:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        superadmin_id = await insert_user(engine, "SUPERADMIN")
        operador_id = await insert_user(engine, "OPERADOR")
        encargado_id = await insert_user(engine, "ENCARGADO")
        events = [
            make_event(status=EventStatus.SCHEDULED),
            make_event(status=EventStatus.AWAITING_BALANCE),
            make_event(status=EventStatus.SCHEDULED),
        ]
        app = create_app()
        try:
            await insert_quotes(engine, [event.quote_id for event in events])
            async with factory() as session:
                session.add_all([event_to_model(event) for event in events])
                await session.commit()

            async def session_override():
                async with factory() as session:
                    yield session

            payments = RecordingPayments(
                {events[0].id: Money(Decimal("980.50")), events[1].id: Money(Decimal("1000"))}
            )
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[containers.get_user_repository] = lambda: (
                SQLAlchemyUserRepository(factory)
            )
            app.dependency_overrides[get_clock_port] = FixedClock
            app.dependency_overrides[get_pre_show_payment_verification_port] = lambda: payments
            app.dependency_overrides[get_crew_schedule_read_port] = lambda: (
                FakeCrewScheduleReadAdapter(
                    assigned_events_by_user={operador_id: frozenset({events[1].id})}
                )
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                for index, role, subject in (
                    (0, Role.SUPERADMIN, superadmin_id),
                    (1, Role.OPERADOR, operador_id),
                ):
                    token = create_access_token(
                        subject=str(subject), role=role.value, secret_key=get_settings().secret_key
                    )
                    response = await client.post(
                        f"/api/v1/events/{events[index].id}/start",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert response.status_code == 200
                    assert response.json()["actual_start_time"] == "2026-10-15T21:35:00Z"
                token = create_access_token(
                    subject=str(encargado_id),
                    role=Role.ENCARGADO.value,
                    secret_key=get_settings().secret_key,
                )
                auth = {"Authorization": f"Bearer {token}"}
                assert (
                    await client.post(f"/api/v1/events/{events[2].id}/start", headers=auth)
                ).status_code == 400
                assert (
                    await client.post(f"/api/v1/events/{events[0].id}/start", headers=auth)
                ).status_code == 409
            async with factory() as session:
                for index in (0, 1):
                    row = await session.get(EventModel, events[index].id)
                    assert row.status == "IN_PROGRESS"
                    assert row.actual_start_time == STARTED_AT
                    assert row.pre_show_balance_paid == (
                        Decimal("980.50") if index == 0 else Decimal("1000")
                    )
                row = await session.get(EventModel, events[2].id)
                assert row.status == "SCHEDULED"
                assert row.actual_start_time is None
                assert row.pre_show_balance_paid == 0
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(exercise())


def test_failed_commit_rolls_back_entire_start_and_releases_lock(database_url: str) -> None:
    run_migrations(database_url)

    async def exercise() -> None:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        event = make_event(
            status=EventStatus.SCHEDULED, pre_show_balance_paid=Money(Decimal("100"))
        )
        actor = ScheduleActor(uuid4(), Role.ENCARGADO)
        payments = RecordingPayments({event.id: Money(Decimal("980.50"))})
        try:
            await insert_quotes(engine, [event.quote_id])
            async with factory() as session:
                session.add(event_to_model(event))
                await session.commit()
            async with factory() as session:

                def reject_commit(_session):
                    raise RuntimeError("commit failed")

                sqlalchemy_event.listen(session.sync_session, "before_commit", reject_commit)
                use_case = StartEventUseCase(
                    sqlalchemy_event_repository.SqlAlchemyEventRepository(session),
                    payments,
                    FakeCrewScheduleReadAdapter(),
                    FixedClock(),
                )
                with pytest.raises(RuntimeError, match="commit failed"):
                    await use_case.execute(event.id, actor)
                assert not session.in_transaction()
                sqlalchemy_event.remove(session.sync_session, "before_commit", reject_commit)
            async with factory() as session:
                row = await session.get(EventModel, event.id)
                assert row.status == "SCHEDULED"
                assert row.actual_start_time is None
                assert row.pre_show_balance_paid == Decimal("100")
            async with factory() as session:
                use_case = StartEventUseCase(
                    sqlalchemy_event_repository.SqlAlchemyEventRepository(session),
                    payments,
                    FakeCrewScheduleReadAdapter(),
                    FixedClock(),
                )
                assert (
                    await asyncio.wait_for(use_case.execute(event.id, actor), timeout=5)
                ).status is EventStatus.IN_PROGRESS
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_concurrent_starts_have_one_winner_and_one_payment_check(database_url: str) -> None:
    run_migrations(database_url)

    async def exercise() -> None:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        event = make_event(status=EventStatus.SCHEDULED)
        actor = ScheduleActor(uuid4(), Role.ENCARGADO)
        first_verified, release_first, second_query = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        queries = 0

        class BlockingPayments(RecordingPayments):
            async def get_verified_balance_total(self, event_id):
                amount = await super().get_verified_balance_total(event_id)
                first_verified.set()
                await release_first.wait()
                return amount

        payments = BlockingPayments({event.id: Money(Decimal("980.50"))})

        def observe_queries(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal queries
            if "FOR UPDATE" in statement:
                queries += 1
                if queries == 2:
                    second_query.set()

        async def attempt(clock):
            async with factory() as session:
                use_case = StartEventUseCase(
                    sqlalchemy_event_repository.SqlAlchemyEventRepository(session),
                    payments,
                    FakeCrewScheduleReadAdapter(),
                    clock,
                )
                try:
                    return await use_case.execute(event.id, actor)
                except InvalidEventStateError as exc:
                    return exc

        tasks = []
        try:
            await insert_quotes(engine, [event.quote_id])
            async with factory() as session:
                session.add(event_to_model(event))
                await session.commit()
            sqlalchemy_event.listen(engine.sync_engine, "before_cursor_execute", observe_queries)
            tasks.append(asyncio.create_task(attempt(FixedClock())))
            await asyncio.wait_for(first_verified.wait(), timeout=5)
            tasks.append(
                asyncio.create_task(attempt(FixedClock(STARTED_AT + timedelta(minutes=1))))
            )
            await asyncio.wait_for(second_query.wait(), timeout=5)
            assert not tasks[1].done()
            release_first.set()
            winner, loser = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
            assert winner.actual_start_time == STARTED_AT
            assert isinstance(loser, InvalidEventStateError)
            assert payments.calls == [event.id]
            async with factory() as session:
                row = (
                    await session.execute(select(EventModel).where(EventModel.id == event.id))
                ).scalar_one()
                assert row.actual_start_time == STARTED_AT
                assert row.status == "IN_PROGRESS"
                assert row.pre_show_balance_paid == Decimal("980.50")
        finally:
            release_first.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await engine.dispose()

    asyncio.run(exercise())
