"""Puerto de salida de lectura del catálogo (E3, entregable del Sprint 0/ola 1).

Contrato que el cotizador (E1) y otras épicas consumen para mostrar paquetes,
temáticas y extras y para conocer el inventario que consume un paquete. La
implementación concreta (SQLAlchemy) vive en la capa de infraestructura.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.application.dtos.catalog_dto import (
    ExtraDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)


class ICatalogReadPort(ABC):
    """Lectura del catálogo para consumidores internos (bot, disponibilidad)."""

    @abstractmethod
    async def list_packages(self, *, include_inactive: bool = False) -> Sequence[PackageReadDTO]:
        """Lista los paquetes con sus temáticas compatibles."""

    @abstractmethod
    async def get_package(self, package_id: UUID) -> PackageReadDTO | None:
        """Devuelve un paquete por id, o ``None`` si no existe."""

    @abstractmethod
    async def list_themes(self, *, include_inactive: bool = False) -> Sequence[ThemeDTO]:
        """Lista las temáticas disponibles."""

    @abstractmethod
    async def get_theme(self, theme_id: UUID) -> ThemeDTO | None:
        """Devuelve una temática por id, o ``None`` si no existe."""

    @abstractmethod
    async def list_extras(self, *, include_inactive: bool = False) -> Sequence[ExtraDTO]:
        """Lista los extras disponibles con su precio de venta."""

    @abstractmethod
    async def get_extra(self, extra_id: UUID) -> ExtraDTO | None:
        """Devuelve un extra por id, o ``None`` si no existe."""

    @abstractmethod
    async def get_inventory_requirements(
        self, package_id: UUID
    ) -> Sequence[InventoryRequirementDTO]:
        """Devuelve el inventario que consume un paquete por evento."""

    @abstractmethod
    async def are_themes_compatible(self, package_id: UUID, theme_id: UUID) -> bool:
        """Indica si una temática es compatible con un paquete (``package_themes``)."""
