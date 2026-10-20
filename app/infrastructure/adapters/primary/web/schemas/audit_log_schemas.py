"""Esquemas de la API de la bitácora de auditoría (US-24)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogReadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    action: str
    entity_name: str
    entity_id: UUID
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    created_at: datetime


class AuditLogPageResponse(BaseModel):
    items: list[AuditLogReadResponse]
    page: int
    page_size: int
    total: int
