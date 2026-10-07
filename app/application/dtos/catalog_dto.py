"""DTOs de lectura del catálogo (capa de aplicación).

Objetos de transferencia agnósticos de framework y de persistencia. El puerto de
lectura del catálogo los devuelve para que el cotizador (E1) muestre paquetes,
temáticas y extras sin conocer las tablas.

No incluyen ``direct_cost``: los costos fijos solo se exponen en el panel
administrativo y nunca a los consumidores públicos o al bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.value_objects.service_category import ServiceCategory


@dataclass(frozen=True)
class ThemeDTO:
    """Temática disponible para configurar un paquete."""

    id: UUID
    name: str
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class ExtraDTO:
    """Extra contratable con su precio de venta."""

    id: UUID
    name: str
    sale_price: Decimal
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class PackageReadDTO:
    """Paquete base con sus temáticas compatibles."""

    id: UUID
    name: str
    service_category: ServiceCategory
    base_price: Decimal
    duration_minutes: int
    description: str | None = None
    compatible_themes: tuple[ThemeDTO, ...] = ()
    is_active: bool = True


@dataclass(frozen=True)
class InventoryItemDTO:
    """Ítem de inventario con su stock total."""

    id: UUID
    name: str
    service_category: ServiceCategory
    total_stock: int
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class InventoryRequirementDTO:
    """Unidades de un ítem de inventario que consume un paquete por evento."""

    inventory_item_id: UUID
    quantity: int
    name: str | None = None


@dataclass(frozen=True)
class CrewDTO:
    """Elenco freelance con el usuario operador vinculado, si existe."""

    id: UUID
    leader_name: str
    phone: str
    service_category: ServiceCategory
    user_id: UUID | None = None
    is_active: bool = True
