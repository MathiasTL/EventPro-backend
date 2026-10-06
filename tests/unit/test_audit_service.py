"""Servicio de auditoría con puerto en memoria (contrato E2 para las demás épicas)."""

import uuid

import pytest

from app.application.services.audit_service import AuditService, InvalidAuditActionError
from app.domain.entities.audit_log import AuditLog


class FakeAuditPort:
    def __init__(self) -> None:
        self.entries: list[AuditLog] = []

    async def record(self, entry: AuditLog) -> None:
        self.entries.append(entry)


async def test_record_persists_valid_entry() -> None:
    port = FakeAuditPort()
    service = AuditService(port)
    entity_id = uuid.uuid4()
    user_id = uuid.uuid4()

    entry = await service.record(
        action="AUDIT_PAYMENT",
        entity_name="payments",
        entity_id=entity_id,
        user_id=user_id,
        old_values={"status": "PENDING"},
        new_values={"status": "VERIFIED"},
    )

    assert len(port.entries) == 1
    stored = port.entries[0]
    assert stored.id == entry.id
    assert stored.action == "AUDIT_PAYMENT"
    assert stored.entity_name == "payments"
    assert stored.entity_id == entity_id
    assert stored.user_id == user_id
    assert stored.old_values == {"status": "PENDING"}
    assert stored.new_values == {"status": "VERIFIED"}


async def test_record_defaults_are_optional() -> None:
    port = FakeAuditPort()
    service = AuditService(port)

    entry = await service.record(
        action="CONTRACT_SIGNED",
        entity_name="contracts",
        entity_id=uuid.uuid4(),
    )

    assert entry.user_id is None
    assert entry.old_values is None
    assert entry.new_values is None
    assert len(port.entries) == 1


async def test_record_rejects_unknown_action() -> None:
    port: FakeAuditPort = FakeAuditPort()
    service = AuditService(port)

    with pytest.raises(InvalidAuditActionError):
        await service.record(
            action="NOT_A_REAL_ACTION",
            entity_name="quotes",
            entity_id=uuid.uuid4(),
        )

    assert port.entries == []
