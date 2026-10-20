"""Entidades del dominio del catálogo y los elencos (E3).

Modelos puros de Python sin dependencias de framework ni de persistencia. Contienen
las invariantes de negocio: precios y duraciones positivos, stock no negativo y el
subconjunto de categorías permitido para el inventario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.domain.exceptions.resource_exceptions import (
    InvalidServiceCategoryError,
    ValidationError,
)
from app.domain.value_objects.money import Money
from app.domain.value_objects.service_category import (
    INVENTORY_SERVICE_CATEGORIES,
    ServiceCategory,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _require_text(value: str, field_name: str) -> None:
    _require(bool(value and value.strip()), f"{field_name} no puede estar vacío")


@dataclass
class Package:
    """Paquete base comercializado por la promotora."""

    name: str
    service_category: ServiceCategory
    base_price: Money
    direct_cost: Money
    duration_minutes: int = 60
    description: str | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require(
            self.base_price.amount > 0,
            "base_price debe ser mayor que cero",
        )
        _require(
            self.direct_cost.amount >= 0,
            "direct_cost no puede ser negativo",
        )
        _require(
            self.duration_minutes > 0,
            "duration_minutes debe ser mayor que cero",
        )

    def deactivate(self) -> None:
        """Baja lógica del paquete."""

        self.is_active = False


@dataclass
class Theme:
    """Temática decorativa o conceptual aplicable a los paquetes."""

    name: str
    description: str | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_text(self.name, "name")

    def deactivate(self) -> None:
        """Baja lógica de la temática."""

        self.is_active = False


@dataclass
class Extra:
    """Elemento adicional contratable (muñecos, bailarines, efectos)."""

    name: str
    sale_price: Money
    direct_cost: Money
    description: str | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require(
            self.sale_price.amount >= 0,
            "sale_price no puede ser negativo",
        )
        _require(
            self.direct_cost.amount >= 0,
            "direct_cost no puede ser negativo",
        )

    def deactivate(self) -> None:
        """Baja lógica del extra."""

        self.is_active = False


@dataclass
class InventoryItem:
    """Ítem de inventario físico con stock limitado (toldos, decoración)."""

    name: str
    service_category: ServiceCategory
    total_stock: int
    description: str | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        if self.service_category not in INVENTORY_SERVICE_CATEGORIES:
            raise InvalidServiceCategoryError("inventory_items solo admite DECORATION o TENTS")
        _require(
            self.total_stock >= 0,
            "total_stock no puede ser negativo",
        )

    def deactivate(self) -> None:
        """Baja lógica del ítem de inventario."""

        self.is_active = False


@dataclass
class Crew:
    """Elenco o proveedor freelance asignable a eventos."""

    leader_name: str
    phone: str
    service_category: ServiceCategory
    user_id: UUID | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_text(self.leader_name, "leader_name")
        _require_text(self.phone, "phone")

    def deactivate(self) -> None:
        """Desactiva el elenco para nuevas asignaciones."""

        self.is_active = False

    def link_user(self, user_id: UUID) -> None:
        """Vincula el elenco con un usuario ``OPERADOR``."""

        self.user_id = user_id

    def unlink_user(self) -> None:
        """Desvincula el elenco del usuario operador."""

        self.user_id = None
