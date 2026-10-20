"""Flujo de autenticación E2E contra PostgreSQL real (testcontainers)."""

import uuid

import httpx
from httpx import ASGITransport
from sqlalchemy import text

from app.core.security import hash_password
from app.main import app

PASSWORD = "PasswordSeguro123!"
_HASHED_PASSWORD = hash_password(PASSWORD)


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, json=json, headers=headers)


async def _seed_user(*, role: str = "ENCARGADO", is_active: bool = True) -> str:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    email = f"auth-{uuid.uuid4().hex[:10]}@eventpro.pe"
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
                "INSERT INTO users (role_id, full_name, email, phone, hashed_password, is_active) "
                "SELECT id, :name, :email, :phone, :password, :active "
                "FROM roles WHERE code = :role"
            ),
            {
                "name": "Usuario Auth",
                "email": email,
                "phone": phone,
                "password": _HASHED_PASSWORD,
                "active": is_active,
                "role": role,
            },
        )
        await session.commit()
    return email


async def _login(email: str) -> httpx.Response:
    return await _request("POST", "/api/v1/auth/login", json={"email": email, "password": PASSWORD})


async def test_login_ok(infra: None) -> None:
    email = await _seed_user(role="OPERADOR")
    response = await _login(email)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert isinstance(body["access_token"], str)
    assert isinstance(body["refresh_token"], str)
    assert body["user"]["role"] == "OPERADOR"
    assert body["user"]["full_name"] == "Usuario Auth"


async def test_login_wrong_password_is_invalid_credentials(infra: None) -> None:
    email = await _seed_user()
    response = await _request(
        "POST", "/api/v1/auth/login", json={"email": email, "password": "OtraClave123!"}
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "https://errors.eventpro.pe/invalid-credentials"
    assert body["status"] == 401
    assert body["instance"] == "/api/v1/auth/login"


async def test_login_unknown_email_is_invalid_credentials(infra: None) -> None:
    response = await _request(
        "POST",
        "/api/v1/auth/login",
        json={"email": "nadie@eventpro.pe", "password": PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["type"] == "https://errors.eventpro.pe/invalid-credentials"


async def test_login_inactive_user_is_403(infra: None) -> None:
    email = await _seed_user(is_active=False)
    response = await _login(email)

    assert response.status_code == 403
    assert response.json()["type"] == "https://errors.eventpro.pe/user-inactive"


async def test_login_validation_error_is_problem_json(infra: None) -> None:
    response = await _request("POST", "/api/v1/auth/login", json={"email": "corto"})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "https://errors.eventpro.pe/validation-error"
    assert any(error["field"] == "body.password" for error in body["errors"])


async def test_refresh_rotates_tokens(infra: None) -> None:
    email = await _seed_user()
    login = (await _login(email)).json()

    first = await _request(
        "POST", "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert first.status_code == 200
    rotated = first.json()
    assert rotated["refresh_token"] != login["refresh_token"]
    assert rotated["expires_in"] == 3600
    assert "user" not in rotated

    replay = await _request(
        "POST", "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["type"] == "https://errors.eventpro.pe/invalid-credentials"


async def test_refresh_rejects_unknown_token(infra: None) -> None:
    response = await _request(
        "POST", "/api/v1/auth/refresh", json={"refresh_token": uuid.uuid4().hex}
    )

    assert response.status_code == 401


async def test_logout_revokes_refresh_token(infra: None) -> None:
    email = await _seed_user()
    login = (await _login(email)).json()
    auth = {"Authorization": f"Bearer {login['access_token']}"}

    first = await _request(
        "POST", "/api/v1/auth/logout", json={"refresh_token": login["refresh_token"]}, headers=auth
    )
    assert first.status_code == 204
    assert first.content == b""

    again = await _request(
        "POST", "/api/v1/auth/logout", json={"refresh_token": login["refresh_token"]}, headers=auth
    )
    assert again.status_code == 204

    refresh = await _request(
        "POST", "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert refresh.status_code == 401


async def test_logout_requires_access_token(infra: None) -> None:
    response = await _request(
        "POST", "/api/v1/auth/logout", json={"refresh_token": uuid.uuid4().hex}
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_logout_rejects_invalid_access_token(infra: None) -> None:
    response = await _request(
        "POST",
        "/api/v1/auth/logout",
        json={"refresh_token": uuid.uuid4().hex},
        headers={"Authorization": "Bearer token-falso"},
    )

    assert response.status_code == 401
