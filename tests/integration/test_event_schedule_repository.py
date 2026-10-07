"""Filtros SQL y endpoint real con enriquecimiento desacoplado."""

import asyncio
from datetime import date, time
from uuid import UUID, uuid4

import httpx
import pytest
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
from app.infrastructure.di.containers import get_crew_schedule_read_port
from app.main import create_app
from tests.event_support import make_event

from ._support import insert_quotes, run_migrations

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

            user_id = uuid4()
            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[get_crew_schedule_read_port] = lambda: (
                FakeCrewScheduleReadAdapter(
                    assigned_events_by_user={user_id: frozenset({events[2].id})}
                )
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                for role, expected in (
                    (Role.ENCARGADO, [1, 2]),
                    (Role.SUPERADMIN, [1, 2]),
                    (Role.OPERADOR, [2]),
                ):
                    token = create_access_token(
                        subject=str(user_id), role=role.value, secret_key=get_settings().secret_key
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
                    assert response.json()[0]["client_name"] == "Cliente pendiente de integración"
                    assert response.json()[0]["client_observations"] is None
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(exercise())
