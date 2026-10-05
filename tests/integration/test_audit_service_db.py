"""Servicio de auditoría E2E: escritura real en audit_logs (JSONB + restricciones)."""

import uuid

import pytest
from sqlalchemy import text as sql_text

from app.application.services.audit_service import AuditService, InvalidAuditActionError
from app.infrastructure.di.containers import get_audit_service


async def _count_entries() -> int:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    async with get_sessionmaker()() as session:
        result = await session.execute(sql_text("SELECT count(*) FROM audit_logs"))
        return int(result.scalar_one())


async def test_audit_entry_is_persisted_with_jsonb(infra: None) -> None:
    service: AuditService = get_audit_service()
    entity_id = uuid.uuid4()

    entry = await service.record(
        action="APPROVE_OVERBOOKED_PAYMENT",
        entity_name="payments",
        entity_id=entity_id,
        old_values={"status": "REQUIRES_MANUAL_APPROVAL", "attempt": 1},
        new_values={"status": "VERIFIED"},
    )

    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                sql_text(
                    "SELECT action, entity_name, entity_id, user_id, old_values, new_values "
                    "FROM audit_logs WHERE id = :id"
                ),
                {"id": entry.id},
            )
        ).one()
    assert row.action == "APPROVE_OVERBOOKED_PAYMENT"
    assert row.entity_name == "payments"
    assert row.entity_id == entity_id
    assert row.user_id is None
    assert row.old_values == {"status": "REQUIRES_MANUAL_APPROVAL", "attempt": 1}
    assert row.new_values == {"status": "VERIFIED"}


async def test_unknown_action_is_rejected_without_writing(infra: None) -> None:
    service = get_audit_service()
    before = await _count_entries()

    with pytest.raises(InvalidAuditActionError):
        await service.record(
            action="NOT_A_REAL_ACTION",
            entity_name="quotes",
            entity_id=uuid.uuid4(),
        )

    assert await _count_entries() == before
