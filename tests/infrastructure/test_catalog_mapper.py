"""Pruebas unitarias del mapeo ORM → DTO del catálogo (sin base de datos)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.domain.value_objects.service_category import ServiceCategory
from app.infrastructure.adapters.secondary.persistence.mappers import catalog_mapper
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    InventoryItemModel,
    PackageInventoryItemModel,
    PackageModel,
    ThemeModel,
)


def test_theme_to_dto() -> None:
    theme = ThemeModel(id=uuid4(), name="Selva", description="Safari", is_active=True)
    dto = catalog_mapper.theme_to_dto(theme)
    assert dto.name == "Selva"
    assert dto.description == "Safari"
    assert dto.is_active


def test_package_to_dto_with_themes() -> None:
    theme = ThemeModel(id=uuid4(), name="Selva Salvaje (Safari)", is_active=True)
    package = PackageModel(
        id=uuid4(),
        name="Hora Loca Medium",
        service_category="SHOW",
        description=None,
        base_price=Decimal("750.00"),
        direct_cost=Decimal("400.00"),
        duration_minutes=60,
        is_active=True,
        themes=[theme],
    )
    dto = catalog_mapper.package_to_dto(package)
    assert dto.name == "Hora Loca Medium"
    assert dto.service_category is ServiceCategory.SHOW
    assert dto.base_price == Decimal("750.00")
    assert dto.duration_minutes == 60
    assert [t.name for t in dto.compatible_themes] == ["Selva Salvaje (Safari)"]


def test_package_to_dto_without_themes() -> None:
    package = PackageModel(
        id=uuid4(),
        name="Servicio de DJ y Luces Pro",
        service_category="DJ",
        base_price=Decimal("600.00"),
        direct_cost=Decimal("350.00"),
        duration_minutes=240,
        is_active=True,
    )
    dto = catalog_mapper.package_to_dto(package)
    assert dto.compatible_themes == ()
    assert dto.service_category is ServiceCategory.DJ


def test_extra_to_dto() -> None:
    extra = ExtraModel(
        id=uuid4(),
        name="Muñeco Gorila Gigante",
        description="Inflable",
        sale_price=Decimal("250.00"),
        direct_cost=Decimal("120.00"),
        is_active=True,
    )
    dto = catalog_mapper.extra_to_dto(extra)
    assert dto.name == "Muñeco Gorila Gigante"
    assert dto.sale_price == Decimal("250.00")


def test_inventory_item_to_dto() -> None:
    item = InventoryItemModel(
        id=uuid4(),
        name="Toldo Estándar 3x3 m",
        service_category="TENTS",
        total_stock=10,
        description=None,
        is_active=True,
    )
    dto = catalog_mapper.inventory_item_to_dto(item)
    assert dto.service_category is ServiceCategory.TENTS
    assert dto.total_stock == 10


def test_requirement_to_dto() -> None:
    inventory_item = InventoryItemModel(
        id=uuid4(),
        name="Kit de Ambientación Estándar",
        service_category="DECORATION",
        total_stock=6,
        is_active=True,
    )
    link = PackageInventoryItemModel(
        id=uuid4(),
        package_id=uuid4(),
        inventory_item_id=inventory_item.id,
        quantity=1,
        inventory_item=inventory_item,
    )
    dto = catalog_mapper.requirement_to_dto(link)
    assert dto.inventory_item_id == inventory_item.id
    assert dto.quantity == 1
    assert dto.name == "Kit de Ambientación Estándar"
