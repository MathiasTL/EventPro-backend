from typing import Protocol

from app.domain.entities.audit_log import AuditLog


class IAuditLogPort(Protocol):
    async def record(self, entry: AuditLog) -> None:
        """Persiste una entrada en la bitácora de auditoría."""
