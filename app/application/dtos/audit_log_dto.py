"""Contratos de aplicación para la bitácora de auditoría (US-24)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class AuditLogFilters:
    action: str | None = None
    entity_name: str | None = None
    entity_id: UUID | None = None
    user_id: UUID | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class AuditLogReadDTO:
    id: UUID
    user_id: UUID | None
    action: str
    entity_name: str
    entity_id: UUID
    old_values: dict[str, object] | None
    new_values: dict[str, object] | None
    created_at: datetime


@dataclass(frozen=True)
class AuditLogPageDTO:
    items: list[AuditLogReadDTO]
    page: int
    page_size: int
    total: int
