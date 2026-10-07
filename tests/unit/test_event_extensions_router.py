from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.application.dtos.event_occupancy_dto import EventOccupancy
from app.application.use_cases.event.register_event_extension import RegisterEventExtensionUseCase
from app.application.use_cases.event.settle_event import SettleEventUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import get_auth_context
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)
from app.infrastructure.di import containers
from app.main import create_app
from tests.event_support import make_event
from tests.extension_support import PNG_BYTES, FakeExtensionRepository
from tests.start_event_support import FixedClock

USER_ID = uuid4()


def auth(role=Role.ENCARGADO, expires=60):
    token = create_access_token(
        subject=str(USER_ID),
        role=role.value,
        secret_key=get_settings().secret_key,
        expires_minutes=expires,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def setup(tmp_path):
    event = make_event(
        status=EventStatus.IN_PROGRESS, pre_show_balance_paid=Money(Decimal("980.50"))
    )
    repo = FakeExtensionRepository((event,))
    storage = LocalEvidenceStorage(tmp_path, allowed_mime={"image/jpeg", "image/png", "image/webp"})
    crews = FakeCrewScheduleReadAdapter(assigned_events_by_user={USER_ID: frozenset({event.id})})
    app = create_app()
    app.dependency_overrides[containers.get_register_event_extension_use_case] = lambda: (
        RegisterEventExtensionUseCase(repo, storage, crews, FixedClock())
    )
    app.dependency_overrides[containers.get_settle_event_use_case] = lambda: SettleEventUseCase(
        repo, crews
    )
    yield app, event, repo, storage
    app.dependency_overrides.clear()


async def extension(
    app,
    event_id,
    *,
    headers=None,
    data=None,
    evidence=PNG_BYTES,
    filename="evidence.png",
    mime="image/png",
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            f"/api/v1/events/{event_id}/extensions",
            headers=headers,
            data=data
            if data is not None
            else {"extra_minutes": "30", "agreed_rate": "100", "payment_method": "YAPE"},
            files={"evidence_file": (filename, evidence, mime)} if evidence is not None else None,
        )


async def settle(app, event_id, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(f"/api/v1/events/{event_id}/settle", **kwargs)


@pytest.mark.parametrize("role", list(Role))
async def test_extension_contract_and_settlement(setup, role):
    app, event, repo, storage = setup
    response = await extension(app, event.id, headers=auth(role))
    assert response.status_code == 201
    payment = repo.payments[0]
    assert response.json() == {
        "event_id": str(event.id),
        "status": "EXTENDED",
        "extension_id": str(repo.extensions[0].id),
        "payment": {
            "payment_id": str(payment.id),
            "concept": "EXTENSION",
            "amount": 100.0,
            "validation_status": "VERIFIED",
            "audit_status": "UNREVIEWED",
        },
    }
    assert await storage.open(payment.evidence_path) == PNG_BYTES
    response = await settle(app, event.id, headers=auth(role), json={})
    assert response.status_code == 200
    assert response.json() == {"event_id": str(event.id), "status": "SETTLED"}
    assert (await extension(app, event.id, headers=auth(role))).status_code == 409
    assert (await settle(app, event.id, headers=auth(role))).status_code == 409


@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer bad"}, auth(expires=-1)])
async def test_authentication_required(setup, headers):
    app, event, repo, _ = setup
    assert (await extension(app, event.id, headers=headers)).status_code == 401
    assert (await settle(app, event.id, headers=headers)).status_code == 401
    assert repo.loads == []


@pytest.mark.parametrize("existing", [True, False])
async def test_operator_outside_scope_returns_404_before_load(setup, existing):
    app, event, repo, storage = setup
    crews = FakeCrewScheduleReadAdapter()
    app.dependency_overrides[containers.get_register_event_extension_use_case] = lambda: (
        RegisterEventExtensionUseCase(repo, storage, crews, FixedClock())
    )
    app.dependency_overrides[containers.get_settle_event_use_case] = lambda: SettleEventUseCase(
        repo, crews
    )
    event_id = event.id if existing else uuid4()
    assert (await extension(app, event_id, headers=auth(Role.OPERADOR))).status_code == 404
    assert (await settle(app, event_id, headers=auth(Role.OPERADOR))).status_code == 404
    assert repo.loads == []


async def test_missing_event_and_uuid_validation(setup):
    app, _, _, _ = setup
    for event_id, expected in ((uuid4(), 404), ("invalid", 422)):
        assert (await extension(app, event_id, headers=auth())).status_code == expected
        assert (await settle(app, event_id, headers=auth())).status_code == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra_minutes", "0"),
        ("extra_minutes", "1.5"),
        ("extra_minutes", "2147483648"),
        ("agreed_rate", "0"),
        ("agreed_rate", "NaN"),
        ("agreed_rate", "1.001"),
        ("payment_method", "UNKNOWN"),
        ("unexpected", "1"),
    ],
)
async def test_invalid_forms_have_no_side_effects(setup, field, value):
    app, event, repo, _ = setup
    data = {"extra_minutes": "30", "agreed_rate": "100", "payment_method": "YAPE", field: value}
    response = await extension(app, event.id, headers=auth(), data=data)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "El cuerpo o los parámetros no cumplen el esquema."
    assert "errors.pydantic.dev" not in response.text
    assert '"input"' not in response.text
    assert '"ctx"' not in response.text
    assert repo.saves == repo.payments == []


@pytest.mark.parametrize(
    "evidence",
    [None, b"", b"plain text", b"%PDF-1.4\n1234", PNG_BYTES + b"0" * (5 * 1024 * 1024)],
    ids=["missing", "empty", "text", "pdf", "oversize"],
)
async def test_evidence_is_required_image_and_bounded(setup, evidence):
    app, event, repo, _ = setup
    response = await extension(app, event.id, headers=auth(), evidence=evidence)
    assert response.status_code == 422
    if evidence is not None:
        assert response.json()["type"].endswith("/invalid-file")
    assert repo.payments == []


async def test_settlement_checks_coverage_and_rejects_client_fields(setup):
    app, event, repo, _ = setup
    assert (await settle(app, event.id, headers=auth(), json={"paid": True})).status_code == 422
    repo.events[event.id].pre_show_balance_paid = Money.zero()
    response = await settle(app, event.id, headers=auth())
    assert response.status_code == 400
    assert response.json()["type"].endswith("/balance-pending")
    assert repo.saves == []


async def test_settlement_rejects_inconsistent_extension_totals(setup):
    app, event, repo, _ = setup
    repo.events[event.id].extra_hours_amount = Money(Decimal("100"))
    response = await settle(app, event.id, headers=auth())
    assert response.status_code == 409
    assert response.json()["type"].endswith("/extension-payment-mismatch")


def test_openapi_documents_multipart_and_responses(setup):
    app, _, _, _ = setup
    paths = app.openapi()["paths"]
    operation = paths["/api/v1/events/{event_id}/extensions"]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]
    assert {"201", "401", "403", "404", "409", "422"} <= set(operation["responses"])
    assert "200" in paths["/api/v1/events/{event_id}/settle"]["post"]["responses"]


async def test_disallowed_role_is_forbidden_before_use_case(setup):
    from types import SimpleNamespace

    app, event, repo, _ = setup
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(
        user_id=USER_ID, role="CLIENTE"
    )
    assert (await extension(app, event.id)).status_code == 403
    assert (await settle(app, event.id)).status_code == 403
    assert repo.loads == []


async def test_resource_conflict_is_409_and_compensates_evidence(setup, tmp_path):
    app, event, repo, _ = setup

    async def occupancy(event, added_minutes):
        return EventOccupancy(simultaneous_windows=(event.time_window,) * 3)

    repo.load_occupancy = occupancy
    response = await extension(app, event.id, headers=auth())
    assert response.status_code == 409
    assert response.json()["type"].endswith("/extension-resource-conflict")
    assert "aprobación manual" in response.json()["detail"]
    assert repo.payments == []
    assert list((tmp_path / "evidence").iterdir()) == []


async def test_invalid_data_on_settled_event_returns_422_before_load(setup):
    app, event, repo, _ = setup
    repo.events[event.id].status = EventStatus.SETTLED
    response = await extension(
        app,
        event.id,
        headers=auth(),
        data={"extra_minutes": "30", "agreed_rate": "0", "payment_method": "CASH"},
    )
    assert response.status_code == 422
    assert repo.loads == []
    assert repo.locks == 0
