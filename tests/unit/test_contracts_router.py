from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest

from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.persistence.database import get_contract_write_session
from app.infrastructure.di.containers import get_contract_use_case
from app.main import create_app
from tests import auth_support
from tests.contract_support import setup_contracts


async def no_transaction() -> AsyncIterator[None]:
    yield None


@pytest.fixture
async def api():
    app = create_app()
    service, repo, _, _, _ = setup_contracts()
    auth_support.install(app)
    app.dependency_overrides[get_contract_use_case] = lambda: service
    app.dependency_overrides[get_contract_write_session] = no_transaction
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        yield client, repo


def headers(role=Role.ENCARGADO):
    auth_support.set_role(role)
    token = create_access_token(
        subject=str(uuid4()), role=role, secret_key=get_settings().secret_key, expires_minutes=60
    )
    return {"Authorization": f"Bearer {token}"}


async def test_full_management_http_flow_hides_secrets(api):
    client, repo = api
    auth = headers()
    issued = await client.post(
        "/api/v1/contracts", json={"event_id": str(repo.data.event_id)}, headers=auth
    )
    assert issued.status_code == 200, issued.text
    body = issued.json()
    for secret in [
        "signature_token_hash",
        "otp_hash",
        "pdf_storage_path",
        "sealed_pdf_storage_path",
    ]:
        assert secret not in body
    key = body["contract_id"]
    assert (await client.get(f"/api/v1/contracts/{key}", headers=auth)).status_code == 200
    page = await client.get("/api/v1/contracts?status=ISSUED&is_manual_mode=false", headers=auth)
    assert page.json()["total"] == 1
    pdf = await client.get(f"/api/v1/contracts/{key}/pdf", headers=auth)
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["cache-control"] == "private, no-store"
    assert (
        await client.post(f"/api/v1/contracts/{key}/resend-link", headers=auth)
    ).status_code == 200
    changed = await client.patch(
        f"/api/v1/contracts/{key}/observations",
        json={"client_observations": "Sin ruido"},
        headers=auth,
    )
    assert changed.status_code == 200
    voided = await client.post(
        f"/api/v1/contracts/{key}/void", json={"reason": "Cambio del cliente"}, headers=auth
    )
    assert voided.json()["status"] == "VOIDED"
    assert (
        await client.post(f"/api/v1/contracts/{key}/resend-link", headers=auth)
    ).status_code == 409


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "", None),
        ("POST", "", {"event_id": str(uuid4())}),
        ("GET", "/id", None),
        ("GET", "/id/pdf", None),
        ("POST", "/id/resend-link", None),
        ("POST", "/id/void", {"reason": "Cambio"}),
        ("PATCH", "/id/observations", {"client_observations": None}),
    ],
)
async def test_all_routes_require_auth_and_staff(api, method, path, payload):
    client, _ = api
    url = "/api/v1/contracts" + path.replace("/id", f"/{uuid4()}")
    assert (await client.request(method, url, json=payload)).status_code == 401
    assert (
        await client.request(method, url, json=payload, headers=headers(Role.OPERADOR))
    ).status_code == 403


async def test_errors_are_problem_json_and_validate_inputs(api):
    client, _ = api
    auth = headers(Role.SUPERADMIN)
    unknown = await client.get(f"/api/v1/contracts/{uuid4()}", headers=auth)
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/problem+json")
    assert (await client.get("/api/v1/contracts?page_size=101", headers=auth)).status_code == 422
    assert (
        await client.post("/api/v1/contracts", json={"event_id": "no"}, headers=auth)
    ).status_code == 422
