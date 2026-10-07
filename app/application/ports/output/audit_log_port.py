from collections.abc import Sequence
from typing import Protocol

from app.application.dtos.audit_log_dto import AuditLogFilters
from app.domain.entities.audit_log import AuditLog


class IAuditLogPort(Protocol):
    async def record(self, entry: AuditLog) -> None:
        """Persiste una entrada en la bitácora de auditoría."""

    async def list_entries(self, filters: AuditLogFilters) -> Sequence[AuditLog]:
        """Devuelve las entradas que cumplen los filtros, de más reciente a más antigua."""

    async def count_entries(self, filters: AuditLogFilters) -> int:
        """Cuenta las entradas que cumplen los filtros."""
