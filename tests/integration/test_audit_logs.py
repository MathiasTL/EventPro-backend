"""Lectura de la bitácora de auditoría E2E contra PostgreSQL real (testcontainers)."""

import uuid
from datetime import UTC, datetime, timedelta

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
    params: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, json=json, params=params, headers=headers)


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


async def _user_id(email: str) -> uuid.UUID:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    async with get_sessionmaker()() as session:
        result = await session.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
        value = result.scalar_one()
    return uuid.UUID(str(value))


async def _login(role: str) -> tuple[str, uuid.UUID]:
    email = await _seed_user(role=role)
    user_id = await _user_id(email)
    login = await _request(
        "POST", "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return str(login.json()["access_token"]), user_id


async def _access_token(role: str) -> str:
    token, _ = await _login(role)
    return token


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

    entry_day = datetime.fromisoformat(match["created_at"]).date()
    same_day = await _request(
        "GET",
        "/api/v1/audit-logs",
        params={
            "entity_id": str(entity_id),
            "from_date": str(entry_day),
            "to_date": str(entry_day),
        },
        headers=auth,
    )
    assert same_day.status_code == 200, same_day.text
    assert same_day.json()["total"] == 1
    assert same_day.json()["items"][0]["id"] == str(entry.id)

    next_day = await _request(
        "GET",
        "/api/v1/audit-logs",
        params={"entity_id": str(entity_id), "from_date": str(entry_day + timedelta(days=1))},
        headers=auth,
    )
    assert next_day.json()["total"] == 0

    previous_day = await _request(
        "GET",
        "/api/v1/audit-logs",
        params={"entity_id": str(entity_id), "to_date": str(entry_day - timedelta(days=1))},
        headers=auth,
    )
    assert previous_day.json()["total"] == 0

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


async def test_max_to_date_does_not_fail(infra: None) -> None:
    """Regresión [P2]: `to_date=9999-12-31` no debe provocar un 500 por OverflowError."""
    token = await _access_token(role="SUPERADMIN")
    auth = {"Authorization": f"Bearer {token}"}
    entity_id = uuid.uuid4()

    entry = await get_audit_service().record(
        action="MANUAL_CONTRACT", entity_name="contracts", entity_id=entity_id
    )

    response = await _request(
        "GET",
        "/api/v1/audit-logs",
        params={"entity_id": str(entity_id), "to_date": "9999-12-31"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(entry.id)


async def _purge_audit_entries(entity_name: str) -> None:
    """Deja la bitácora como estaba: `test_bootstrap_superadmin` borra todos los users."""
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    async with get_sessionmaker()() as session:
        await session.execute(
            text("DELETE FROM audit_logs WHERE entity_name = :entity_name"),
            {"entity_name": entity_name},
        )
        await session.commit()


async def test_user_filter_and_pagination(infra: None) -> None:
    token, user_id = await _login(role="ENCARGADO")
    auth = {"Authorization": f"Bearer {token}"}
    entity_name = f"probe-{uuid.uuid4().hex[:8]}"

    recorded = [
        await get_audit_service().record(
            action="AUDIT_PAYMENT",
            entity_name=entity_name,
            entity_id=uuid.uuid4(),
            user_id=user_id if index % 2 == 0 else None,
        )
        for index in range(5)
    ]
    expected = [str(entry.id) for entry in recorded]

    try:
        filtered = await _request(
            "GET",
            "/api/v1/audit-logs",
            params={"entity_name": entity_name, "user_id": str(user_id)},
            headers=auth,
        )
        assert filtered.status_code == 200, filtered.text
        expected_owned = {expected[0], expected[2], expected[4]}
        assert filtered.json()["total"] == 3
        assert {item["id"] for item in filtered.json()["items"]} == expected_owned

        seen: list[str] = []
        for page in (1, 2, 3):
            response = await _request(
                "GET",
                "/api/v1/audit-logs",
                params={"entity_name": entity_name, "page": page, "page_size": 2},
                headers=auth,
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 5
            assert body["page"] == page
            assert len(body["items"]) == (1 if page == 3 else 2)
            seen.extend(item["id"] for item in body["items"])

        assert len(set(seen)) == 5
        assert seen == list(reversed(expected))
    finally:
        await _purge_audit_entries(entity_name)


async def test_equal_created_at_are_tie_broken_by_id(infra: None) -> None:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    token = await _access_token(role="SUPERADMIN")
    auth = {"Authorization": f"Bearer {token}"}
    entity_name = f"tie-{uuid.uuid4().hex[:8]}"
    moment = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    row_ids = [uuid.uuid4() for _ in range(3)]
    insert_sql = (
        "INSERT INTO audit_logs (id, action, entity_name, entity_id, created_at) "
        "VALUES (:id, 'MANUAL_CONTRACT', :entity_name, :entity_id, :moment)"
    )
    order_sql = (
        "SELECT id FROM audit_logs WHERE entity_name = :entity_name "
        "ORDER BY created_at DESC, id DESC"
    )

    async with get_sessionmaker()() as session:
        for row_id in row_ids:
            await session.execute(
                text(insert_sql),
                {
                    "id": row_id,
                    "entity_name": entity_name,
                    "entity_id": uuid.uuid4(),
                    "moment": moment,
                },
            )
        result = await session.execute(text(order_sql), {"entity_name": entity_name})
        expected_order = [str(value) for value in result.scalars().all()]
        await session.commit()

    single_page = await _request(
        "GET", "/api/v1/audit-logs", params={"entity_name": entity_name}, headers=auth
    )
    assert single_page.status_code == 200, single_page.text
    assert [item["id"] for item in single_page.json()["items"]] == expected_order

    first = await _request(
        "GET",
        "/api/v1/audit-logs",
        params={"entity_name": entity_name, "page": 1, "page_size": 2},
        headers=auth,
    )
    second = await _request(
        "GET",
        "/api/v1/audit-logs",
        params={"entity_name": entity_name, "page": 2, "page_size": 2},
        headers=auth,
    )
    assert first.json()["total"] == 3
    assert second.json()["total"] == 3
    paged = [item["id"] for item in first.json()["items"] + second.json()["items"]]
    assert paged == expected_order
    assert len(set(paged)) == 3
