from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.use_cases.event.start_event import StartEventUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from app.infrastructure.di.containers import get_start_event_use_case
from app.main import create_app
from tests.auth_support import install, set_role
from tests.event_support import make_event
from tests.start_event_support import FakeStartEventRepository, FixedClock, RecordingPayments

USER_ID = uuid4()


def headers(role: Role = Role.ENCARGADO, *, expires: int = 60) -> dict[str, str]:
    set_role(role)
    token = create_access_token(
        subject=str(USER_ID),
        role=role.value,
        secret_key=get_settings().secret_key,
        expires_minutes=expires,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def setup() -> Iterator[tuple[FastAPI, FakeStartEventRepository, RecordingPayments]]:
    event = make_event(status=EventStatus.SCHEDULED)
    repo = FakeStartEventRepository((event,))
    payments = RecordingPayments({event.id: Money(Decimal("980.50"))})
    crews = FakeCrewScheduleReadAdapter(assigned_events_by_user={USER_ID: frozenset({event.id})})
    app = create_app()
    install(app)
    app.dependency_overrides[get_start_event_use_case] = lambda: StartEventUseCase(
        repo, payments, crews, FixedClock()
    )
    yield app, repo, payments
    app.dependency_overrides.clear()


async def post(app: FastAPI, event_id: object, **kwargs: object) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(f"/api/v1/events/{event_id}/start", **kwargs)


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.SUPERADMIN, Role.OPERADOR])
@pytest.mark.parametrize("body", [None, {}])
async def test_start_accepts_empty_body_and_returns_utc(setup, role: Role, body) -> None:
    app, repo, _ = setup
    event_id = next(iter(repo.events))
    response = await post(app, event_id, headers=headers(role), json=body)
    assert response.status_code == 200
    assert response.json() == {
        "event_id": str(event_id),
        "status": "IN_PROGRESS",
        "actual_start_time": "2026-10-15T21:35:00Z",
    }


@pytest.mark.parametrize(
    "body", [{"amount": 980.50}, {"paid": True}, {"actual_start_time": "2026-10-15T21:00:00Z"}, []]
)
async def test_client_cannot_supply_payment_or_start_time(setup, body) -> None:
    app, repo, payments = setup
    response = await post(app, next(iter(repo.events)), headers=headers(), json=body)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert repo.saves == payments.calls == []


@pytest.mark.parametrize("auth", [None, {"Authorization": "Bearer bad"}, headers(expires=-1)])
async def test_start_requires_valid_authentication(setup, auth) -> None:
    app, repo, payments = setup
    response = await post(app, next(iter(repo.events)), headers=auth)
    assert response.status_code == 401
    assert repo.loads == payments.calls == []


@pytest.mark.parametrize("missing", [False, True])
async def test_operator_outside_scope_gets_403_before_load(setup, missing: bool) -> None:
    app, repo, payments = setup
    event_id = uuid4() if missing else next(iter(repo.events))
    app.dependency_overrides[get_start_event_use_case] = lambda: StartEventUseCase(
        repo, payments, FakeCrewScheduleReadAdapter(), FixedClock()
    )
    response = await post(app, event_id, headers=headers(Role.OPERADOR))
    assert response.status_code == 403
    assert response.json()["type"] == "https://errors.eventpro.pe/forbidden"
    assert repo.loads == payments.calls == []


async def test_unknown_event_returns_404(setup) -> None:
    app, _, _ = setup
    response = await post(app, uuid4(), headers=headers())
    assert response.status_code == 404
    assert response.json()["type"] == "https://errors.eventpro.pe/not-found"


async def test_unverified_balance_returns_400_and_keeps_state(setup) -> None:
    app, repo, _ = setup
    event_id = next(iter(repo.events))
    repo.events[event_id].pre_show_balance_paid = Money(Decimal("980.50"))
    app.dependency_overrides[get_start_event_use_case] = lambda: StartEventUseCase(
        repo, RecordingPayments(), FakeCrewScheduleReadAdapter(), FixedClock()
    )
    response = await post(app, event_id, headers=headers())
    assert response.status_code == 400
    assert response.json()["type"] == "https://errors.eventpro.pe/balance-pending"
    assert repo.saves == []
    assert repo.events[event_id].actual_start_time is None


async def test_second_start_returns_409_without_overwrite(setup) -> None:
    app, repo, payments = setup
    event_id = next(iter(repo.events))
    assert (await post(app, event_id, headers=headers())).status_code == 200
    response = await post(app, event_id, headers=headers())
    assert response.status_code == 409
    assert response.json()["type"] == "https://errors.eventpro.pe/invalid-event-state"
    assert payments.calls == [event_id]
    assert len(repo.saves) == 1


async def test_invalid_uuid_returns_422(setup) -> None:
    app, _, _ = setup
    assert (await post(app, "not-a-uuid", headers=headers())).status_code == 422


def test_start_openapi_documents_response_and_rejects_extra_body_fields(setup) -> None:
    app, _, _ = setup
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/events/{event_id}/start"]["post"]
    assert set(operation["responses"]) >= {"200", "400", "401", "403", "404", "409", "422"}
    assert schema["components"]["schemas"]["StartEventRequest"]["additionalProperties"] is False
