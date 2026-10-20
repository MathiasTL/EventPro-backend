"""Consulta paginada de la bitácora de auditoría."""

from app.application.dtos.audit_log_dto import AuditLogFilters, AuditLogPageDTO, AuditLogReadDTO
from app.application.ports.output.audit_log_port import IAuditLogPort


class ListAuditLogsUseCase:
    def __init__(self, audit_logs: IAuditLogPort) -> None:
        self._audit_logs = audit_logs

    async def execute(self, filters: AuditLogFilters) -> AuditLogPageDTO:
        items = await self._audit_logs.list_entries(filters)
        total = await self._audit_logs.count_entries(filters)
        ready = [
            AuditLogReadDTO(
                id=item.id,
                user_id=item.user_id,
                action=item.action,
                entity_name=item.entity_name,
                entity_id=item.entity_id,
                old_values=item.old_values,
                new_values=item.new_values,
                created_at=item.created_at,
            )
            for item in items
        ]
        return AuditLogPageDTO(
            items=ready, page=filters.page, page_size=filters.page_size, total=total
        )
