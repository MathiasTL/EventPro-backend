"""Esquemas HTTP del módulo de catálogo (RF-03, RF-04)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.value_objects.service_category import ServiceCategory


class ThemeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str | None = None


class ThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    is_active: bool = True


class ExtraRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    sale_price: Decimal = Field(ge=0)
    direct_cost: Decimal = Field(ge=0)
    description: str | None = None


class ExtraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    sale_price: Decimal
    description: str | None = None
    is_active: bool = True
    direct_cost: Decimal | None = None


class InventoryItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    service_category: ServiceCategory
    total_stock: int = Field(ge=0)
    description: str | None = None


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    service_category: ServiceCategory
    total_stock: int
    description: str | None = None
    is_active: bool = True


class PackageInventoryItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inventory_item_id: UUID
    quantity: int = Field(gt=0)


class PackageInventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inventory_item_id: UUID
    quantity: int
    name: str | None = None


class PackageInventoryItemsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PackageInventoryItemRequest] = Field(default_factory=list)


class PackageInventoryItemsResponse(BaseModel):
    package_id: UUID
    items: list[PackageInventoryItemResponse] = Field(default_factory=list)


class PackageThemesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_ids: list[UUID] = Field(default_factory=list)


class PackageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    service_category: ServiceCategory
    base_price: Decimal = Field(gt=0)
    direct_cost: Decimal = Field(ge=0)
    duration_minutes: int = Field(gt=0)
    description: str | None = None


class PackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    service_category: ServiceCategory
    base_price: Decimal
    duration_minutes: int
    description: str | None = None
    is_active: bool = True
    direct_cost: Decimal | None = None
    compatible_themes: list[ThemeResponse] = Field(default_factory=list)
    inventory_items: list[PackageInventoryItemResponse] = Field(default_factory=list)


class ThemeListResponse(BaseModel):
    items: list[ThemeResponse]
    total: int


class ExtraListResponse(BaseModel):
    items: list[ExtraResponse]
    total: int


class InventoryItemListResponse(BaseModel):
    items: list[InventoryItemResponse]
    total: int


class PackageListResponse(BaseModel):
    items: list[PackageResponse]
    total: int
