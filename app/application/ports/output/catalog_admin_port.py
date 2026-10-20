"""Puertos de salida de administración del catálogo y los elencos (E3).

Contrato de escritura del catálogo (RF-03, RF-04) y de gestión de elencos (RF-29).
La lectura la expone ``ICatalogReadPort``. La validación de invariantes de negocio
ocurre en el dominio antes de invocar a estos puertos.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from app.application.dtos.catalog_dto import (
    CrewDTO,
    ExtraDTO,
    InventoryItemDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.domain.entities.catalog import Crew, Extra, InventoryItem, Package, Theme


class ICatalogAdminPort(ABC):
    """Escritura del catálogo comercial (paquetes, temáticas, extras, inventario)."""

    @abstractmethod
    async def create_package(self, package: Package) -> PackageReadDTO:
        """Registra un paquete nuevo."""

    @abstractmethod
    async def update_package(self, package: Package) -> PackageReadDTO:
        """Actualiza los datos de un paquete existente."""

    @abstractmethod
    async def deactivate_package(self, package_id: UUID) -> PackageReadDTO:
        """Baja lógica de un paquete."""

    @abstractmethod
    async def set_package_inventory_items(
        self, package_id: UUID, items: Sequence[tuple[UUID, int]]
    ) -> Sequence[InventoryRequirementDTO]:
        """Reemplaza el inventario que consume el paquete (lista vacía = no consume)."""

    @abstractmethod
    async def set_package_themes(
        self, package_id: UUID, theme_ids: Sequence[UUID]
    ) -> Sequence[ThemeDTO]:
        """Reemplaza las temáticas compatibles del paquete."""

    @abstractmethod
    async def create_theme(self, theme: Theme) -> ThemeDTO:
        """Registra una temática nueva."""

    @abstractmethod
    async def update_theme(self, theme: Theme) -> ThemeDTO:
        """Actualiza una temática existente."""

    @abstractmethod
    async def deactivate_theme(self, theme_id: UUID) -> ThemeDTO:
        """Baja lógica de una temática."""

    @abstractmethod
    async def create_extra(self, extra: Extra) -> ExtraDTO:
        """Registra un extra nuevo."""

    @abstractmethod
    async def update_extra(self, extra: Extra) -> ExtraDTO:
        """Actualiza un extra existente."""

    @abstractmethod
    async def deactivate_extra(self, extra_id: UUID) -> ExtraDTO:
        """Baja lógica de un extra."""

    @abstractmethod
    async def create_inventory_item(self, item: InventoryItem) -> InventoryItemDTO:
        """Registra un ítem de inventario nuevo."""

    @abstractmethod
    async def update_inventory_item(self, item: InventoryItem) -> InventoryItemDTO:
        """Actualiza un ítem de inventario (el stock no puede bajar de lo reservado)."""

    @abstractmethod
    async def deactivate_inventory_item(self, item_id: UUID) -> InventoryItemDTO:
        """Baja lógica de un ítem de inventario."""

    @abstractmethod
    async def count_active_package_usage(self, inventory_item_id: UUID) -> int:
        """Cantidad de paquetes activos que consumen el ítem."""

    @abstractmethod
    async def count_future_reserved_units(self, inventory_item_id: UUID) -> int:
        """Unidades reservadas en ventanas futuras (reservas ``ACTIVE``)."""

    @abstractmethod
    async def list_package_direct_costs(self) -> dict[UUID, Decimal]:
        """Costo fijo por paquete (nunca se expone a clientes ni al bot)."""

    @abstractmethod
    async def list_extra_direct_costs(self) -> dict[UUID, Decimal]:
        """Costo fijo por extra (nunca se expone a clientes ni al bot)."""

    @abstractmethod
    async def list_inventory_items(
        self, *, include_inactive: bool = False
    ) -> Sequence[InventoryItemDTO]:
        """Inventario físico registrado (panel administrativo)."""


class ICrewAdminPort(ABC):
    """Gestión de elencos freelance (RF-29)."""

    @abstractmethod
    async def list_crews(self, *, include_inactive: bool = False) -> Sequence[CrewDTO]:
        """Lista los elencos registrados."""

    @abstractmethod
    async def get_crew(self, crew_id: UUID) -> CrewDTO | None:
        """Devuelve un elenco por id, o ``None`` si no existe."""

    @abstractmethod
    async def find_crew_by_user(self, user_id: UUID) -> CrewDTO | None:
        """Devuelve el elenco vinculado a un usuario operador, si existe."""

    @abstractmethod
    async def create_crew(self, crew: Crew) -> CrewDTO:
        """Registra un elenco, opcionalmente vinculado a un usuario operador."""

    @abstractmethod
    async def update_crew(self, crew: Crew) -> CrewDTO:
        """Actualiza un elenco (líder, teléfono, categoría, vínculo o estado)."""
