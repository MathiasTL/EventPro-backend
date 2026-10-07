"""Caso de uso de listado de bitácora aislado del router (seguimiento de revisión)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.application.dtos.audit_log_dto import AuditLogFilters
from app.application.use_cases.audit.list_audit_logs import ListAuditLogsUseCase
from app.domain.entities.audit_log import AuditLog


def _entry(age_seconds: int = 0) -> AuditLog:
    return AuditLog(
        id=uuid.uuid4(),
        action="AUDIT_PAYMENT",
        entity_name="payments",
        entity_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        old_values={"status": "PENDING"},
        new_values={"status": "VERIFIED"},
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC) + timedelta(seconds=age_seconds),
    )


class FakeAuditLogPort:
    def __init__(self, entries: Sequence[AuditLog], *, total: int | None = None) -> None:
        self._entries = list(entries)
        self._total = len(self._entries) if total is None else total
        self.received: list[AuditLogFilters] = []

    async def record(self, entry: AuditLog) -> None:
        self._entries.append(entry)

    async def list_entries(self, filters: AuditLogFilters) -> Sequence[AuditLog]:
        self.received.append(filters)
        return self._entries

    async def count_entries(self, filters: AuditLogFilters) -> int:
        self.received.append(filters)
        return self._total


async def test_execute_maps_dto_and_reuses_filters() -> None:
    entry = _entry()
    port = FakeAuditLogPort([entry], total=7)
    use_case = ListAuditLogsUseCase(port)
    filters = AuditLogFilters(action="AUDIT_PAYMENT", page=3, page_size=5)

    page = await use_case.execute(filters)

    assert port.received == [filters, filters]
    assert (page.page, page.page_size, page.total) == (3, 5, 7)
    assert len(page.items) == 1
    item = page.items[0]
    assert item.id == entry.id
    assert item.user_id == entry.user_id
    assert item.action == "AUDIT_PAYMENT"
    assert item.entity_name == "payments"
    assert item.entity_id == entry.entity_id
    assert item.old_values == {"status": "PENDING"}
    assert item.new_values == {"status": "VERIFIED"}
    assert item.created_at == entry.created_at


async def test_execute_with_empty_result_returns_no_items() -> None:
    port = FakeAuditLogPort([])
    use_case = ListAuditLogsUseCase(port)

    page = await use_case.execute(AuditLogFilters())

    assert page.items == []
    assert page.total == 0
    assert (page.page, page.page_size) == (1, 20)
