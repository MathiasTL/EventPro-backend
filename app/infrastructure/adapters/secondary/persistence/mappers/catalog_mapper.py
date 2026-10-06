"""Transformadores ORM Model → DTO (capa de persistencia)."""

from __future__ import annotations

from app.application.dtos.catalog_dto import (
    ExtraDTO,
    InventoryItemDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.domain.value_objects.service_category import ServiceCategory
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    InventoryItemModel,
    PackageInventoryItemModel,
    PackageModel,
    ThemeModel,
)


def theme_to_dto(theme: ThemeModel) -> ThemeDTO:
    """Convierte una temática ORM a DTO."""

    return ThemeDTO(
        id=theme.id,
        name=theme.name,
        description=theme.description,
        is_active=theme.is_active,
    )


def package_to_dto(package: PackageModel) -> PackageReadDTO:
    """Convierte un paquete ORM (con sus temáticas) a DTO."""

    return PackageReadDTO(
        id=package.id,
        name=package.name,
        service_category=ServiceCategory(package.service_category),
        base_price=package.base_price,
        duration_minutes=package.duration_minutes,
        description=package.description,
        compatible_themes=tuple(theme_to_dto(theme) for theme in package.themes),
        is_active=package.is_active,
    )


def extra_to_dto(extra: ExtraModel) -> ExtraDTO:
    """Convierte un extra ORM a DTO."""

    return ExtraDTO(
        id=extra.id,
        name=extra.name,
        sale_price=extra.sale_price,
        description=extra.description,
        is_active=extra.is_active,
    )


def inventory_item_to_dto(item: InventoryItemModel) -> InventoryItemDTO:
    """Convierte un ítem de inventario ORM a DTO."""

    return InventoryItemDTO(
        id=item.id,
        name=item.name,
        service_category=ServiceCategory(item.service_category),
        total_stock=item.total_stock,
        description=item.description,
        is_active=item.is_active,
    )


def requirement_to_dto(link: PackageInventoryItemModel) -> InventoryRequirementDTO:
    """Convierte un vínculo paquete↔inventario ORM a DTO de requerimiento."""

    return InventoryRequirementDTO(
        inventory_item_id=link.inventory_item_id,
        quantity=link.quantity,
        name=link.inventory_item.name,
    )
