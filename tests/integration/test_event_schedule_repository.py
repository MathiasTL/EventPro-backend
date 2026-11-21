"""Filtros SQL y endpoint real con enriquecimiento desacoplado."""

import asyncio
from datetime import date, time
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.dtos.event_schedule_dto import EventScheduleFilters
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine, get_session
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_repository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_schedule_read_adapters import (  # noqa: E501
    SqlAlchemyCrewScheduleReadAdapter,
    SqlAlchemyQuoteScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.persistence.user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.di import containers
from app.main import create_app
from tests.event_support import make_event

from ._support import insert_quotes, insert_user, run_migrations

pytestmark = pytest.mark.integration


def test_schedule_sql_filters_and_http(database_url: str) -> None:
    run_migrations(database_url)

    async def exercise() -> None:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        events = [
            make_event(event_date=date(2026, 10, 14), status=EventStatus.SCHEDULED),
            make_event(status=EventStatus.SCHEDULED, start_time=time(10), id=UUID(int=1)),
            make_event(status=EventStatus.SCHEDULED, start_time=time(10), id=UUID(int=2)),
            make_event(status=EventStatus.CANCELLED),
            make_event(event_date=date(2026, 10, 16), status=EventStatus.SCHEDULED),
        ]
        app = create_app()
        try:
            await insert_quotes(engine, [event.quote_id for event in events])
            async with factory() as session:
                session.add_all([event_to_model(event) for event in reversed(events)])
                await session.commit()
                repo = sqlalchemy_event_repository.SqlAlchemyEventRepository(session)
                cases = [
                    (EventScheduleFilters(), [0, 1, 2, 3, 4]),
                    (EventScheduleFilters(from_date=date(2026, 10, 15)), [1, 2, 3, 4]),
                    (EventScheduleFilters(to_date=date(2026, 10, 15)), [0, 1, 2, 3]),
                    (EventScheduleFilters(status=EventStatus.SCHEDULED), [0, 1, 2, 4]),
                    (
                        EventScheduleFilters(
                            from_date=date(2026, 10, 15),
                            to_date=date(2026, 10, 15),
                            status=EventStatus.SCHEDULED,
                        ),
                        [1, 2],
                    ),
                    (EventScheduleFilters(from_date=date(2026, 11, 1)), []),
                ]
                for filters, expected in cases:
                    result = await repo.list_for_schedule(filters)
                    assert [event.id for event in result] == [
                        events[index].id for index in expected
                    ]
                assert (
                    await repo.list_for_schedule(EventScheduleFilters(), event_ids=frozenset())
                    == ()
                )
                own = await repo.list_for_schedule(
                    EventScheduleFilters(), event_ids=frozenset({events[2].id})
                )
                assert [event.id for event in own] == [events[2].id]

            async def session_override():
                async with factory() as session:
                    yield session

            encargado_id = await insert_user(engine, "ENCARGADO")
            superadmin_id = await insert_user(engine, "SUPERADMIN")
            operador_id = await insert_user(engine, "OPERADOR")
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[containers.get_user_repository] = lambda: (
                SQLAlchemyUserRepository(factory)
            )
            app.dependency_overrides[containers.get_crew_schedule_read_port] = lambda: (
                FakeCrewScheduleReadAdapter(
                    assigned_events_by_user={operador_id: frozenset({events[2].id})}
                )
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                for role, subject, expected in (
                    (Role.ENCARGADO, encargado_id, [1, 2]),
                    (Role.SUPERADMIN, superadmin_id, [1, 2]),
                    (Role.OPERADOR, operador_id, [2]),
                ):
                    token = create_access_token(
                        subject=str(subject), role=role.value, secret_key=get_settings().secret_key
                    )
                    response = await client.get(
                        "/api/v1/events/schedule",
                        params={
                            "from_date": "2026-10-15",
                            "to_date": "2026-10-15",
                            "status": "SCHEDULED",
                        },
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert response.status_code == 200
                    assert [item["event_id"] for item in response.json()] == [
                        str(events[index].id) for index in expected
                    ]
                    assert response.json()[0]["client_name"] == "Cliente de prueba"
                    assert response.json()[0]["client_observations"] is None
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(exercise())


def test_schedule_reads_real_quote_crew_and_operator_scope(database_url: str) -> None:
    run_migrations(database_url)

    async def exercise() -> None:
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        events = [
            make_event(event_date=date(2027, 1, 11), status=EventStatus.SCHEDULED),
            make_event(event_date=date(2027, 1, 12), status=EventStatus.SCHEDULED),
            make_event(event_date=date(2027, 1, 13), status=EventStatus.SCHEDULED),
        ]
        app = create_app()
        try:
            await insert_quotes(engine, [event.quote_id for event in events])
            active_operator = await insert_user(engine, "OPERADOR")
            inactive_operator = await insert_user(engine, "OPERADOR")
            unassigned_operator = await insert_user(engine, "OPERADOR")
            encargado = await insert_user(engine, "ENCARGADO")
            async with engine.begin() as connection:
                theme_name = f"Selva {events[0].id.hex[:8]}"
                theme_id = await connection.scalar(
                    text("INSERT INTO themes (name) VALUES (:name) RETURNING id"),
                    {"name": theme_name},
                )
                await connection.execute(
                    text("UPDATE quotes SET theme_id=:theme WHERE id=:quote"),
                    {"theme": theme_id, "quote": events[0].quote_id},
                )
                await connection.execute(
                    text(
                        "UPDATE clients SET full_name='Ana Salazar' WHERE id="
                        "(SELECT client_id FROM quotes WHERE id=:quote)"
                    ),
                    {"quote": events[0].quote_id},
                )
                await connection.execute(
                    text(
                        "UPDATE packages SET name='Hora Loca Medium' WHERE id="
                        "(SELECT package_id FROM quotes WHERE id=:quote)"
                    ),
                    {"quote": events[0].quote_id},
                )
                for event in events:
                    await connection.execute(
                        text(
                            "INSERT INTO events "
                            "(id,event_code,quote_id,event_date,start_time,end_time,address,"
                            "district,status,total_services_amount,total_mobility_amount,"
                            "final_total_amount) VALUES "
                            "(:id,:code,:quote,:day,'18:00','19:00','Av. Lima','Lima',"
                            "'SCHEDULED',100,0,100)"
                        ),
                        {
                            "id": event.id,
                            "code": event.event_code,
                            "quote": event.quote_id,
                            "day": event.event_date,
                        },
                    )
                crews = []
                for leader, user, active in (
                    ("Zoe Vega", active_operator, True),
                    ("Ana Torres", None, True),
                    ("Luis Paredes", inactive_operator, False),
                ):
                    crew_id = await connection.scalar(
                        text(
                            "INSERT INTO crews (user_id,leader_name,phone,service_category,"
                            "is_active) VALUES (:user,:leader,:phone,'SHOW',:active) RETURNING id"
                        ),
                        {
                            "user": user,
                            "leader": leader,
                            "phone": f"+519{len(crews) + 1:08d}",
                            "active": active,
                        },
                    )
                    crews.append(crew_id)
                for event_id, crew_id in (
                    (events[0].id, crews[0]),
                    (events[0].id, crews[1]),
                    (events[1].id, crews[2]),
                ):
                    await connection.execute(
                        text(
                            "INSERT INTO crew_assignments (event_id,crew_id) VALUES (:event,:crew)"
                        ),
                        {"event": event_id, "crew": crew_id},
                    )

            async with factory() as session:
                quotes = SqlAlchemyQuoteScheduleReadAdapter(session)
                crew_read = SqlAlchemyCrewScheduleReadAdapter(session)
                missing = UUID(int=999)
                details = await quotes.get_details(frozenset({events[0].quote_id, missing}))
                assert details[events[0].quote_id].client_name == "Ana Salazar"
                assert details[events[0].quote_id].package_name == "Hora Loca Medium"
                assert details[events[0].quote_id].theme_name == theme_name
                assert details[missing].client_name == "Cliente no disponible"
                assert (await quotes.get_details(frozenset())) == {}
                assert (await crew_read.get_crews(frozenset())) == {}
                assert await crew_read.get_assigned_event_ids(active_operator) == frozenset(
                    {events[0].id}
                )
                assert await crew_read.get_assigned_event_ids(inactive_operator) == frozenset()
                crew_details = await crew_read.get_crews(frozenset(event.id for event in events))
                assert [crew.leader_name for crew in crew_details[events[0].id]] == [
                    "Ana Torres",
                    "Zoe Vega",
                ]
                assert crew_details[events[2].id] == ()

            async def session_override():
                async with factory() as session:
                    yield session

            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[containers.get_user_repository] = lambda: (
                SQLAlchemyUserRepository(factory)
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                for role, user_id, status, expected_ids in (
                    (Role.ENCARGADO, encargado, 200, [event.id for event in events]),
                    (Role.OPERADOR, active_operator, 200, [events[0].id]),
                    (Role.OPERADOR, inactive_operator, 403, []),
                    (Role.OPERADOR, unassigned_operator, 403, []),
                ):
                    token = create_access_token(
                        subject=str(user_id), role=role.value, secret_key=get_settings().secret_key
                    )
                    response = await client.get(
                        "/api/v1/events/schedule",
                        params={"from_date": "2027-01-11", "to_date": "2027-01-13"},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert response.status_code == status
                    if status == 200:
                        items = response.json()
                        assert [item["event_id"] for item in items] == [
                            str(event_id) for event_id in expected_ids
                        ]
                        assert items[0]["client_name"] == "Ana Salazar"
                        assert items[0]["package_name"] == "Hora Loca Medium"
                        assert items[0]["theme_name"] == theme_name
                        assert [crew["leader_name"] for crew in items[0]["crews"]] == [
                            "Ana Torres",
                            "Zoe Vega",
                        ]
                        if role is Role.ENCARGADO:
                            assert items[1]["theme_name"] == "Sin temática"
                            assert items[2]["crews"] == []
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(exercise())
