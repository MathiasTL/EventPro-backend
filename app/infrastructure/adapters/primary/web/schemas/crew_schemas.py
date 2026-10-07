"""Esquemas HTTP del módulo de elencos (RF-29)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.value_objects.service_category import ServiceCategory


class CrewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leader_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=20)
    service_category: ServiceCategory
    user_id: UUID | None = None
    is_active: bool = True


class CrewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    leader_name: str
    phone: str
    service_category: ServiceCategory
    user_id: UUID | None = None
    is_active: bool = True


class CrewListResponse(BaseModel):
    items: list[CrewResponse]
    total: int
