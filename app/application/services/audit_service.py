import uuid
from uuid import UUID

from app.application.ports.output.audit_log_port import IAuditLogPort
from app.domain.entities.audit_log import AUDIT_ACTIONS, AuditLog


class InvalidAuditActionError(ValueError):
    """La acción no está en el vocabulario auditables (CHECK de audit_logs)."""

    def __init__(self, action: str) -> None:
        super().__init__(f"Acción de auditoría no permitida: {action}")
        self.action = action


class AuditService:
    """Servicio de auditoría que las demás épicas invocan (contrato E2)."""

    def __init__(self, port: IAuditLogPort) -> None:
        self._port = port

    async def record(
        self,
        *,
        action: str,
        entity_name: str,
        entity_id: UUID,
        user_id: UUID | None = None,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
    ) -> AuditLog:
        if action not in AUDIT_ACTIONS:
            raise InvalidAuditActionError(action)
        entry = AuditLog(
            id=uuid.uuid4(),
            action=action,
            entity_name=entity_name,
            entity_id=entity_id,
            user_id=user_id,
            old_values=old_values,
            new_values=new_values,
        )
        await self._port.record(entry)
        return entry
