"""Gestión de usuarios E2E contra PostgreSQL real (testcontainers)."""

import uuid

import httpx
from httpx import ASGITransport
from sqlalchemy import text

from app.core.security import hash_password
from app.main import app

PATH = "/api/v1/users"
PASSWORD = "PasswordSeguro123!"
_HASHED_PASSWORD = hash_password(PASSWORD)


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
    params: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, json=json, params=params, headers=headers)


async def _seed_user(*, role: str = "SUPERADMIN") -> str:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    email = f"users-{uuid.uuid4().hex[:10]}@eventpro.pe"
    phone = f"+519{uuid.uuid4().int % 10**8:08d}"
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "INSERT INTO roles (code, name) VALUES "
                "('SUPERADMIN', 'Superadministrador'), "
                "('ENCARGADO', 'Encargado'), "
                "('OPERADOR', 'Operador') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        await session.execute(
            text(
                "INSERT INTO users (role_id, full_name, email, phone, hashed_password) "
                "SELECT id, 'Usuario Users', :email, :phone, :password "
                "FROM roles WHERE code = :role"
            ),
            {"email": email, "phone": phone, "password": _HASHED_PASSWORD, "role": role},
        )
        await session.commit()
    return email


async def _login(email: str) -> httpx.Response:
    return await _request("POST", "/api/v1/auth/login", json={"email": email, "password": PASSWORD})


async def _headers_for(email: str) -> dict[str, str]:
    response = await _login(email)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "full_name": "Operador Nuevo",
        "email": f"nuevo-{uuid.uuid4().hex[:8]}@eventpro.pe",
        "phone": f"+519{uuid.uuid4().int % 10**8:08d}",
        "role": "OPERADOR",
        "password": PASSWORD,
    }
    body.update(overrides)
    return body


async def _find_by_email(email: str, headers: dict[str, str]) -> dict[str, object] | None:
    response = await _request("GET", PATH, params={"q": email}, headers=headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    return next((item for item in items if item["email"] == email), None)


async def test_superadmin_creates_lists_reads_and_updates_user(infra: None) -> None:
    headers = await _headers_for(await _seed_user(role="SUPERADMIN"))

    created = await _request("POST", PATH, json=_payload(), headers=headers)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "OPERADOR"
    assert body["is_active"] is True
    assert "password" not in body
    assert "hashed_password" not in body
    user_id = body["id"]

    filtered = await _request(
        "GET", PATH, params={"role": "OPERADOR", "q": body["email"]}, headers=headers
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == user_id

    detail = await _request("GET", f"{PATH}/{user_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["email"] == body["email"]

    patched = await _request(
        "PATCH", f"{PATH}/{user_id}", json={"full_name": "Operador Renombrado"}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["full_name"] == "Operador Renombrado"


async def test_duplicate_email_returns_409(infra: None) -> None:
    headers = await _headers_for(await _seed_user(role="SUPERADMIN"))
    first = _payload()

    created = await _request("POST", PATH, json=first, headers=headers)
    duplicate = await _request(
        "POST",
        PATH,
        json=_payload(email=str(first["email"]).upper(), phone="+519111000222"),
        headers=headers,
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["type"].endswith("duplicate-resource")


async def test_operator_and_anonymous_are_rejected(infra: None) -> None:
    operator_headers = await _headers_for(await _seed_user(role="OPERADOR"))

    forbidden = await _request("GET", PATH, headers=operator_headers)
    anonymous = await _request("GET", PATH)
    unauthorized_post = await _request("POST", PATH, json=_payload())

    assert forbidden.status_code == 403
    assert anonymous.status_code == 401
    assert unauthorized_post.status_code == 401


async def test_deactivating_user_revokes_refresh_tokens(infra: None) -> None:
    superadmin = await _headers_for(await _seed_user(role="SUPERADMIN"))
    operator_email = await _seed_user(role="OPERADOR")
    login = await _login(operator_email)
    assert login.status_code == 200, login.text
    refresh_token = login.json()["refresh_token"]
    operator = await _find_by_email(operator_email, superadmin)
    assert operator is not None

    patched = await _request(
        "PATCH", f"{PATH}/{operator['id']}", json={"is_active": False}, headers=superadmin
    )
    refreshed = await _request(
        "POST", "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False
    assert refreshed.status_code == 401


async def test_superadmin_cannot_disable_or_demote_self(infra: None) -> None:
    email = await _seed_user(role="SUPERADMIN")
    headers = await _headers_for(email)
    me = await _find_by_email(email, headers)
    assert me is not None

    deactivated = await _request(
        "PATCH", f"{PATH}/{me['id']}", json={"is_active": False}, headers=headers
    )
    demoted = await _request(
        "PATCH", f"{PATH}/{me['id']}", json={"role": "OPERADOR"}, headers=headers
    )

    assert deactivated.status_code == 403
    assert demoted.status_code == 403


async def test_unknown_user_returns_404(infra: None) -> None:
    headers = await _headers_for(await _seed_user(role="SUPERADMIN"))

    detail = await _request("GET", f"{PATH}/{uuid.uuid4()}", headers=headers)

    assert detail.status_code == 404
