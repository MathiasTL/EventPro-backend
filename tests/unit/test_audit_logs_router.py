from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.dtos.audit_log_dto import AuditLogFilters
from app.application.use_cases.audit.list_audit_logs import ListAuditLogsUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.entities.audit_log import AuditLog
from app.domain.value_objects.role import Role
from app.infrastructure.di import containers
from app.main import create_app

PATH = "/api/v1/audit-logs"
USER_ID = uuid4()
BASE_TIME = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _entry(
    *,
    action: str = "OVERRIDE_MOBILITY",
    entity_name: str = "quotes",
    entity_id: UUID | None = None,
    user_id: UUID | None = USER_ID,
    age_minutes: int = 0,
) -> AuditLog:
    return AuditLog(
        id=uuid4(),
        action=action,
        entity_name=entity_name,
        entity_id=entity_id or uuid4(),
        user_id=user_id,
        old_values={"amount": 80},
        new_values={"amount": 95},
        created_at=BASE_TIME + timedelta(minutes=age_minutes),
    )


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self._items: list[AuditLog] = []

    async def record(self, entry: AuditLog) -> None:
        self._items.append(entry)

    async def list_entries(self, filters: AuditLogFilters) -> Sequence[AuditLog]:
        rows = self._filtered(filters)
        start = (max(1, filters.page) - 1) * max(1, filters.page_size)
        return tuple(rows[start : start + filters.page_size])

    async def count_entries(self, filters: AuditLogFilters) -> int:
        return len(self._filtered(filters))

    def _filtered(self, filters: AuditLogFilters) -> list[AuditLog]:
        rows = sorted(self._items, key=lambda item: item.created_at, reverse=True)
        if filters.action is not None:
            rows = [row for row in rows if row.action == filters.action]
        if filters.entity_name is not None:
            rows = [row for row in rows if row.entity_name == filters.entity_name]
        if filters.entity_id is not None:
            rows = [row for row in rows if row.entity_id == filters.entity_id]
        if filters.user_id is not None:
            rows = [row for row in rows if row.user_id == filters.user_id]
        if filters.from_date is not None:
            rows = [row for row in rows if row.created_at >= filters.from_date]
        if filters.to_date is not None:
            rows = [row for row in rows if row.created_at <= filters.to_date]
        return rows


def authorization(role: Role = Role.SUPERADMIN) -> dict[str, str]:
    token = create_access_token(
        subject=str(USER_ID), role=role.value, secret_key=get_settings().secret_key
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def web_app() -> Iterator[FastAPI]:
    app = create_app()
    repo = FakeAuditLogRepository()
    for minutes, action in (
        (0, "OVERRIDE_MOBILITY"),
        (5, "AUDIT_PAYMENT"),
        (10, "MANUAL_CONTRACT"),
    ):
        repo._items.append(_entry(action=action, age_minutes=-minutes))
    app.dependency_overrides[containers.get_list_audit_logs_use_case] = lambda: (
        ListAuditLogsUseCase(repo)
    )
    yield app
    app.dependency_overrides.clear()


async def test_requires_access_token(web_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.get(PATH)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_operador_is_forbidden(web_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.get(PATH, headers=authorization(Role.OPERADOR))
    assert response.status_code == 403
    assert response.json()["type"] == "https://errors.eventpro.pe/forbidden"


@pytest.mark.parametrize("role", [Role.SUPERADMIN, Role.ENCARGADO])
async def test_superadmin_and_encargado_can_read(web_app: FastAPI, role: Role) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.get(PATH, headers=authorization(role))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 3
    actions = [item["action"] for item in body["items"]]
    assert actions == ["OVERRIDE_MOBILITY", "AUDIT_PAYMENT", "MANUAL_CONTRACT"]
    first = body["items"][0]
    assert first["old_values"] == {"amount": 80}
    assert first["new_values"] == {"amount": 95}
    assert first["entity_name"] == "quotes"
    assert first["user_id"] == str(USER_ID)


async def test_filters_narrow_the_result(web_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        by_action = await client.get(
            PATH, params={"action": "AUDIT_PAYMENT"}, headers=authorization()
        )
        by_entity = await client.get(
            PATH, params={"entity_name": "payments"}, headers=authorization()
        )
    assert by_action.status_code == 200
    assert by_action.json()["total"] == 1
    assert by_action.json()["items"][0]["action"] == "AUDIT_PAYMENT"
    assert by_entity.json()["total"] == 0


async def test_pagination_slices_and_keeps_total(web_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        first = await client.get(PATH, params={"page": 1, "page_size": 2}, headers=authorization())
        second = await client.get(PATH, params={"page": 2, "page_size": 2}, headers=authorization())
    assert first.json()["total"] == 3
    assert len(first.json()["items"]) == 2
    assert second.json()["total"] == 3
    assert len(second.json()["items"]) == 1
    assert first.json()["items"][0]["action"] != second.json()["items"][0]["action"]


async def test_invalid_pagination_is_rejected(web_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        zero_page = await client.get(PATH, params={"page": 0}, headers=authorization())
        huge_size = await client.get(PATH, params={"page_size": 500}, headers=authorization())
    assert zero_page.status_code == 422
    assert huge_size.status_code == 422


async def test_bitacora_is_read_only(web_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        post = await client.post(PATH, json={}, headers=authorization())
        delete = await client.delete(PATH, headers=authorization())
        patch = await client.patch(f"{PATH}/{uuid4()}", json={}, headers=authorization())
    assert post.status_code == 405
    assert delete.status_code == 405
    assert patch.status_code in (404, 405)
