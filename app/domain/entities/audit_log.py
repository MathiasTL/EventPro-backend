from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

# Vocabulario de acciones auditables (mismo conjunto que el CHECK de audit_logs).
AUDIT_ACTIONS = (
    "OVERRIDE_MOBILITY",
    "OVERRIDE_TRANSIT_INTERVAL",
    "APPROVE_OVERBOOKED_PAYMENT",
    "REJECT_OVERBOOKED_PAYMENT",
    "AUDIT_PAYMENT",
    "MANUAL_CONTRACT",
    "CONTRACT_SIGNED",
    "SEND_CONVERSATION_MESSAGE",
    "OVERRIDE_CONVERSATION_ASSIGNMENT",
)


@dataclass
class AuditLog:
    id: UUID
    action: str
    entity_name: str
    entity_id: UUID
    user_id: UUID | None = None
    old_values: dict[str, object] | None = None
    new_values: dict[str, object] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
