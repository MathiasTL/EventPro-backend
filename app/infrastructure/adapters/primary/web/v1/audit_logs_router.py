"""Router HTTP de la bitácora de auditoría (US-24): solo lectura."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.application.dtos.audit_log_dto import AuditLogFilters
from app.application.use_cases.audit.list_audit_logs import ListAuditLogsUseCase
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.schemas.audit_log_schemas import (
    AuditLogPageResponse,
    AuditLogReadResponse,
)
from app.infrastructure.di import containers

router = APIRouter(prefix="/audit-logs", tags=["Bitácora de auditoría"])


@router.get("", response_model=AuditLogPageResponse)
async def list_audit_logs(
    context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN, Role.ENCARGADO))],
    use_case: Annotated[ListAuditLogsUseCase, Depends(containers.get_list_audit_logs_use_case)],
    action: Annotated[str | None, Query(max_length=50)] = None,
    entity_name: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[UUID | None, Query()] = None,
    user_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AuditLogPageResponse:
    """Devuelve la bitácora paginada y ordenada del más reciente al más antiguo."""
    filters = AuditLogFilters(
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    result = await use_case.execute(filters)
    return AuditLogPageResponse(
        items=[AuditLogReadResponse.model_validate(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )
