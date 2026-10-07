"""Lectura de la bitácora de auditoría E2E contra PostgreSQL real (testcontainers)."""

import uuid

import httpx
from httpx import ASGITransport
from sqlalchemy import text

from app.core.security import hash_password
from app.infrastructure.di.containers import get_audit_service
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


async def _seed_user(*, role: str) -> str:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    email = f"audit-{uuid.uuid4().hex[:10]}@eventpro.pe"
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
                "SELECT id, :name, :email, :phone, :password, true "
                "FROM roles WHERE code = :role"
            ),
            {
                "name": "Usuario Auditoría",
                "email": email,
                "phone": phone,
                "password": _HASHED_PASSWORD,
                "role": role,
            },
        )
        await session.commit()
    return email


async def _access_token(role: str) -> str:
    email = await _seed_user(role=role)
    login = await _request(
        "POST", "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return str(login.json()["access_token"])


async def test_written_entry_is_readable_and_filtered(infra: None) -> None:
    token = await _access_token(role="ENCARGADO")
    auth = {"Authorization": f"Bearer {token}"}
    entity_id = uuid.uuid4()

    entry = await get_audit_service().record(
        action="APPROVE_OVERBOOKED_PAYMENT",
        entity_name="payments",
        entity_id=entity_id,
        new_values={"status": "VERIFIED"},
    )

    all_rows = await _request("GET", "/api/v1/audit-logs", headers=auth)
    assert all_rows.status_code == 200, all_rows.text
    body = all_rows.json()
    assert body["total"] >= 1
    match = next(item for item in body["items"] if item["id"] == str(entry.id))
    assert match["action"] == "APPROVE_OVERBOOKED_PAYMENT"
    assert match["entity_name"] == "payments"
    assert match["entity_id"] == str(entity_id)
    assert match["new_values"] == {"status": "VERIFIED"}
    assert match["user_id"] is None

    filtered = await _request(
        "GET",
        "/api/v1/audit-logs",
        params={"action": "APPROVE_OVERBOOKED_PAYMENT", "entity_id": str(entity_id)},
        headers=auth,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == str(entry.id)

    empty = await _request(
        "GET", "/api/v1/audit-logs", params={"entity_name": "cotizaciones"}, headers=auth
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0


async def test_entries_are_returned_newest_first(infra: None) -> None:
    token = await _access_token(role="SUPERADMIN")
    auth = {"Authorization": f"Bearer {token}"}
    service = get_audit_service()

    first = await service.record(
        action="MANUAL_CONTRACT", entity_name="contracts", entity_id=uuid.uuid4()
    )
    second = await service.record(
        action="CONTRACT_SIGNED", entity_name="contracts", entity_id=uuid.uuid4()
    )

    response = await _request(
        "GET", "/api/v1/audit-logs", params={"entity_name": "contracts"}, headers=auth
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids.index(str(second.id)) < ids.index(str(first.id))


async def test_operador_cannot_read_bitacora(infra: None) -> None:
    token = await _access_token(role="OPERADOR")

    response = await _request(
        "GET", "/api/v1/audit-logs", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json()["type"] == "https://errors.eventpro.pe/forbidden"


async def test_anonymous_is_unauthorized(infra: None) -> None:
    response = await _request("GET", "/api/v1/audit-logs")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
