from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.dtos.event_schedule_dto import CrewScheduleDTO, QuoteScheduleDTO
from app.application.use_cases.event.get_event_schedule import GetEventScheduleUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
    FakeQuoteScheduleReadAdapter,
)
from app.infrastructure.di.containers import get_event_schedule_use_case
from app.main import create_app
from tests.application.test_get_event_schedule import FakeEventRepository
from tests.event_support import make_event

PATH = "/api/v1/events/schedule"
USER_ID = uuid4()
EVENT = make_event(status=EventStatus.SCHEDULED, client_observations="  Sin reggaetón.\n ")


def authorization(role: Role = Role.ENCARGADO) -> dict[str, str]:
    token = create_access_token(
        subject=str(USER_ID), role=role.value, secret_key=get_settings().secret_key
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def web_app() -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_event_schedule_use_case] = lambda: GetEventScheduleUseCase(
        FakeEventRepository([EVENT]), FakeQuoteScheduleReadAdapter(), FakeCrewScheduleReadAdapter()
    )
    yield app
    app.dependency_overrides.clear()


async def request(
    app: FastAPI, *, headers: dict[str, str] | None = None, params: dict[str, str] | None = None
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(PATH, headers=headers, params=params)


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.SUPERADMIN])
async def test_schedule_full_response_and_placeholders(web_app: FastAPI, role: Role) -> None:
    response = await request(web_app, headers=authorization(role))
    assert response.status_code == 200
    assert response.json() == [
        {
            "event_id": str(EVENT.id),
            "event_code": EVENT.event_code,
            "event_date": "2026-10-15",
            "start_time": "21:30",
            "end_time": "22:30",
            "end_date": "2026-10-15",
            "district": "Miraflores",
            "client_name": "Cliente pendiente de integración",
            "package_name": "Paquete pendiente de integración",
            "theme_name": "Temática pendiente de integración",
            "crews": [],
            "client_observations": EVENT.client_observations,
            "status": "SCHEDULED",
            "pending_balance_to_collect": 980.50,
        }
    ]


@pytest.mark.parametrize(
    "params",
    [
        {"from_date": "bad"},
        {"to_date": "2026-02-30"},
        {"status": "UNKNOWN"},
        {"from_date": "2026-10-16", "to_date": "2026-10-15"},
        {"district": "Miraflores"},
        {"theme_id": str(uuid4())},
        {"crew_id": str(uuid4())},
    ],
)
async def test_invalid_or_deferred_filters_return_problem_details(
    web_app: FastAPI, params: dict[str, str]
) -> None:
    response = await request(web_app, headers=authorization(), params=params)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://errors.eventpro.pe/validation-error"


async def test_empty_schedule_is_an_array(web_app: FastAPI) -> None:
    response = await request(web_app, headers=authorization(), params={"status": "CANCELLED"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer invalid"}])
async def test_schedule_requires_authentication(
    web_app: FastAPI, headers: dict[str, str] | None
) -> None:
    response = await request(web_app, headers=headers)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_operator_without_assignments_gets_403(web_app: FastAPI) -> None:
    response = await request(web_app, headers=authorization(Role.OPERADOR))
    assert response.status_code == 403
    assert "asignación activa" in response.json()["detail"]


async def test_operator_only_sees_assigned_events_and_real_fake_details(web_app: FastAPI) -> None:
    other = make_event()
    crew = CrewScheduleDTO(crew_id=uuid4(), leader_name="Luis Torres")
    web_app.dependency_overrides[get_event_schedule_use_case] = lambda: GetEventScheduleUseCase(
        FakeEventRepository([EVENT, other]),
        FakeQuoteScheduleReadAdapter(
            {EVENT.quote_id: QuoteScheduleDTO("Carlos Rodríguez", "Hora Loca Medium", "Selva")}
        ),
        FakeCrewScheduleReadAdapter(
            crews_by_event={EVENT.id: (crew,)},
            assigned_events_by_user={USER_ID: frozenset({EVENT.id})},
        ),
    )
    response = await request(web_app, headers=authorization(Role.OPERADOR))
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["event_id"] == str(EVENT.id)
    assert response.json()[0]["client_name"] == "Carlos Rodríguez"
    assert response.json()[0]["crews"] == [
        {"crew_id": str(crew.crew_id), "leader_name": "Luis Torres"}
    ]


def test_schedule_is_registered_in_openapi(web_app: FastAPI) -> None:
    operation = web_app.openapi()["paths"][PATH]["get"]
    assert {parameter["name"] for parameter in operation["parameters"]} >= {
        "from_date",
        "to_date",
        "status",
        "authorization",
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["type"] == "array"


async def test_schedule_reports_operational_end_date_after_midnight(web_app: FastAPI) -> None:
    event = make_event(status=EventStatus.EXTENDED, extra_minutes_total=150)
    web_app.dependency_overrides[get_event_schedule_use_case] = lambda: GetEventScheduleUseCase(
        FakeEventRepository([event]), FakeQuoteScheduleReadAdapter(), FakeCrewScheduleReadAdapter()
    )
    response = await request(web_app, headers=authorization())
    assert response.status_code == 200
    assert response.json()[0]["end_time"] == "01:00"
    assert response.json()[0]["end_date"] == "2026-10-16"
    assert event.end_time.strftime("%H:%M") == "22:30"
