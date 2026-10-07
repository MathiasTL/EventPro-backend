"""Gestión de usuarios E2E contra PostgreSQL real (testcontainers)."""

import uuid
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

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


async def test_deactivated_user_access_token_stops_working(infra: None) -> None:
    superadmin = await _headers_for(await _seed_user(role="SUPERADMIN"))
    operator_email = await _seed_user(role="OPERADOR")
    operator = await _headers_for(operator_email)
    target = await _find_by_email(operator_email, superadmin)
    assert target is not None

    before = await _request("GET", PATH, headers=operator)
    patched = await _request(
        "PATCH", f"{PATH}/{target['id']}", json={"is_active": False}, headers=superadmin
    )
    after = await _request("GET", PATH, headers=operator)

    assert before.status_code == 403
    assert patched.status_code == 200, patched.text
    assert after.status_code == 401
    assert after.json()["type"].endswith("invalid-credentials")


async def test_demoted_user_access_token_loses_privilege(infra: None) -> None:
    superadmin = await _headers_for(await _seed_user(role="SUPERADMIN"))
    victim_email = await _seed_user(role="SUPERADMIN")
    victim = await _headers_for(victim_email)
    target = await _find_by_email(victim_email, superadmin)
    assert target is not None

    before = await _request("GET", PATH, headers=victim)
    demoted = await _request(
        "PATCH", f"{PATH}/{target['id']}", json={"role": "OPERADOR"}, headers=superadmin
    )
    after = await _request("GET", PATH, headers=victim)

    assert before.status_code == 200
    assert demoted.status_code == 200, demoted.text
    assert after.status_code == 403


async def test_repository_blocks_removing_the_last_superadmin(infra: None) -> None:
    from app.application.dtos.user_dto import UserPatch
    from app.domain.exceptions.resource_exceptions import ValidationError
    from app.domain.value_objects.role import Role
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
    from app.infrastructure.adapters.secondary.persistence.user_repository import (
        SQLAlchemyUserRepository,
    )

    email = await _seed_user(role="SUPERADMIN")
    factory = get_sessionmaker()
    async with factory() as session:
        user_id = await session.scalar(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
        assert user_id is not None
        superseded = (
            (
                await session.execute(
                    text(
                        "UPDATE users SET is_active = false "
                        "WHERE is_active AND id <> :target AND role_id IN "
                        "(SELECT id FROM roles WHERE code = 'SUPERADMIN') RETURNING id"
                    ),
                    {"target": user_id},
                )
            )
            .scalars()
            .all()
        )
        await session.commit()
    try:
        with pytest.raises(ValidationError):
            await SQLAlchemyUserRepository(factory).update(user_id, UserPatch(role=Role.OPERADOR))
        async with factory() as session:
            role_code = await session.scalar(
                text(
                    "SELECT r.code FROM users u JOIN roles r ON r.id = u.role_id WHERE u.id = :id"
                ),
                {"id": user_id},
            )
        assert role_code == "SUPERADMIN"
    finally:
        if superseded:
            async with factory() as session:
                await session.execute(
                    text("UPDATE users SET is_active = true WHERE id = ANY(:ids)"),
                    {"ids": list(superseded)},
                )
                await session.commit()


async def test_failed_token_revocation_rolls_back_the_update(infra: None) -> None:
    from app.application.dtos.user_dto import UserPatch
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
    from app.infrastructure.adapters.secondary.persistence.user_repository import (
        SQLAlchemyUserRepository,
    )

    email = await _seed_user(role="OPERADOR")
    factory = get_sessionmaker()
    async with factory() as session:
        user_id = await session.scalar(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
        assert user_id is not None

    with (
        patch(
            "app.infrastructure.adapters.secondary.persistence.user_repository"
            "._revoke_refresh_tokens",
            side_effect=RuntimeError("fallo simulado de revocación"),
        ),
        pytest.raises(RuntimeError),
    ):
        await SQLAlchemyUserRepository(factory).update(
            user_id, UserPatch(is_active=False, revoke_refresh_tokens=True)
        )

    async with factory() as session:
        is_active = await session.scalar(
            text("SELECT is_active FROM users WHERE id = :id"), {"id": user_id}
        )
    assert is_active is True


async def test_database_rejects_duplicate_email_and_phone(infra: None) -> None:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    email = f"unicidad-{uuid.uuid4().hex[:10]}@eventpro.pe"
    phone = f"+519{uuid.uuid4().int % 10**8:08d}"
    factory = get_sessionmaker()
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO roles (code, name) VALUES "
                "('ENCARGADO', 'Encargado'), ('OPERADOR', 'Operador') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        await session.execute(
            text(
                "INSERT INTO users (role_id, full_name, email, phone, hashed_password) "
                "SELECT id, 'Unicidad', :email, :phone, :password "
                "FROM roles WHERE code = 'OPERADOR'"
            ),
            {"email": email, "phone": phone, "password": _HASHED_PASSWORD},
        )
        await session.commit()

    async with factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO users (role_id, full_name, email, phone, hashed_password) "
                    "SELECT id, 'Unicidad duplicada', :email, :phone, :password "
                    "FROM roles WHERE code = 'ENCARGADO'"
                ),
                {
                    "email": email.upper(),
                    "phone": f"+518{uuid.uuid4().int % 10**8:08d}",
                    "password": _HASHED_PASSWORD,
                },
            )
            await session.commit()
        await session.rollback()

    async with factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO users (role_id, full_name, email, phone, hashed_password) "
                    "SELECT id, 'Unicidad duplicada', :email, :phone, :password "
                    "FROM roles WHERE code = 'ENCARGADO'"
                ),
                {
                    "email": f"otro-{uuid.uuid4().hex[:10]}@eventpro.pe",
                    "phone": phone,
                    "password": _HASHED_PASSWORD,
                },
            )
            await session.commit()
        await session.rollback()
