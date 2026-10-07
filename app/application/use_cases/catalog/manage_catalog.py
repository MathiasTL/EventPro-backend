"""Gestión del catálogo comercial (RF-03, RF-04).

Alta, edición y baja lógica de paquetes, temáticas, extras e inventario. Las
invariantes de negocio (precios, duración, categoría de inventario) las valida el
dominio; aquí se orquestan el puerto de escritura y las reglas de uso.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from app.application.dtos.catalog_dto import (
    ExtraDTO,
    InventoryItemDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.application.ports.output.catalog_admin_port import ICatalogAdminPort
from app.domain.entities.catalog import Extra, InventoryItem, Package, Theme
from app.domain.exceptions.resource_exceptions import ResourceInUseError, ValidationError
from app.domain.value_objects.money import Money
from app.domain.value_objects.service_category import ServiceCategory


class ManageCatalogUseCase:
    """Administración de los elementos del catálogo."""

    def __init__(self, catalog: ICatalogAdminPort) -> None:
        self._catalog = catalog

    # --- Paquetes ---

    async def create_package(
        self,
        *,
        name: str,
        service_category: ServiceCategory,
        base_price: Decimal,
        direct_cost: Decimal,
        duration_minutes: int,
        description: str | None = None,
    ) -> PackageReadDTO:
        package = Package(
            name=name,
            service_category=service_category,
            base_price=Money(base_price),
            direct_cost=Money(direct_cost),
            duration_minutes=duration_minutes,
            description=description,
        )
        return await self._catalog.create_package(package)

    async def update_package(
        self,
        package_id: UUID,
        *,
        name: str,
        service_category: ServiceCategory,
        base_price: Decimal,
        direct_cost: Decimal,
        duration_minutes: int,
        description: str | None = None,
    ) -> PackageReadDTO:
        package = Package(
            name=name,
            service_category=service_category,
            base_price=Money(base_price),
            direct_cost=Money(direct_cost),
            duration_minutes=duration_minutes,
            description=description,
            id=package_id,
        )
        return await self._catalog.update_package(package)

    async def deactivate_package(self, package_id: UUID) -> PackageReadDTO:
        return await self._catalog.deactivate_package(package_id)

    async def set_package_inventory_items(
        self, package_id: UUID, items: Sequence[tuple[UUID, int]]
    ) -> Sequence[InventoryRequirementDTO]:
        for _, quantity in items:
            if quantity <= 0:
                raise ValidationError("quantity debe ser mayor que cero")
        return await self._catalog.set_package_inventory_items(package_id, tuple(items))

    async def set_package_themes(
        self, package_id: UUID, theme_ids: Sequence[UUID]
    ) -> Sequence[ThemeDTO]:
        return await self._catalog.set_package_themes(package_id, tuple(theme_ids))

    # --- Temáticas ---

    async def create_theme(self, *, name: str, description: str | None = None) -> ThemeDTO:
        return await self._catalog.create_theme(Theme(name=name, description=description))

    async def update_theme(
        self, theme_id: UUID, *, name: str, description: str | None = None
    ) -> ThemeDTO:
        return await self._catalog.update_theme(
            Theme(name=name, description=description, id=theme_id)
        )

    async def deactivate_theme(self, theme_id: UUID) -> ThemeDTO:
        return await self._catalog.deactivate_theme(theme_id)

    # --- Extras ---

    async def create_extra(
        self,
        *,
        name: str,
        sale_price: Decimal,
        direct_cost: Decimal,
        description: str | None = None,
    ) -> ExtraDTO:
        extra = Extra(
            name=name,
            sale_price=Money(sale_price),
            direct_cost=Money(direct_cost),
            description=description,
        )
        return await self._catalog.create_extra(extra)

    async def update_extra(
        self,
        extra_id: UUID,
        *,
        name: str,
        sale_price: Decimal,
        direct_cost: Decimal,
        description: str | None = None,
    ) -> ExtraDTO:
        extra = Extra(
            name=name,
            sale_price=Money(sale_price),
            direct_cost=Money(direct_cost),
            description=description,
            id=extra_id,
        )
        return await self._catalog.update_extra(extra)

    async def deactivate_extra(self, extra_id: UUID) -> ExtraDTO:
        return await self._catalog.deactivate_extra(extra_id)

    # --- Inventario ---

    async def create_inventory_item(
        self,
        *,
        name: str,
        service_category: ServiceCategory,
        total_stock: int,
        description: str | None = None,
    ) -> InventoryItemDTO:
        item = InventoryItem(
            name=name,
            service_category=service_category,
            total_stock=total_stock,
            description=description,
        )
        return await self._catalog.create_inventory_item(item)

    async def update_inventory_item(
        self,
        inventory_item_id: UUID,
        *,
        name: str,
        service_category: ServiceCategory,
        total_stock: int,
        description: str | None = None,
    ) -> InventoryItemDTO:
        reserved = await self._catalog.count_future_reserved_units(inventory_item_id)
        if total_stock < reserved:
            raise ResourceInUseError(
                "El stock no puede bajar de las unidades ya reservadas en fechas futuras."
            )
        item = InventoryItem(
            name=name,
            service_category=service_category,
            total_stock=total_stock,
            description=description,
            id=inventory_item_id,
        )
        return await self._catalog.update_inventory_item(item)

    async def deactivate_inventory_item(self, inventory_item_id: UUID) -> InventoryItemDTO:
        in_use_by_packages = await self._catalog.count_active_package_usage(inventory_item_id)
        reserved = await self._catalog.count_future_reserved_units(inventory_item_id)
        if in_use_by_packages > 0 or reserved > 0:
            raise ResourceInUseError(
                "El ítem está consumido por paquetes activos o tiene reservas activas futuras."
            )
        return await self._catalog.deactivate_inventory_item(inventory_item_id)
