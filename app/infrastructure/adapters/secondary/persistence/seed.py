"""Sembrado idempotente del catálogo y los roles (Sprint 0, E3 + roles base).

Ejecutable con ``python -m app.infrastructure.adapters.secondary.persistence.seed``.
Verifica la existencia de cada registro antes de insertarlo, por lo que puede
ejecutarse varias veces sin duplicar datos.

Fuente de los datos: ``Docs/03-datos/03-estrategia-migraciones-y-seeds.md`` §2.

.. note::
   La matriz de compatibilidad paquete ↔ temática (``package_themes``) **no** se
   siembra: el documento de seeds no la define y se gestiona desde el panel del
   encargado. Tampoco se siembran elencos (``crews``); se registran por UI.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
from app.infrastructure.adapters.secondary.persistence.models import Role
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    InventoryItemModel,
    PackageInventoryItemModel,
    PackageModel,
    ThemeModel,
)

# --- Roles del sistema (UUID fijos del documento de seeds) ---
ROLES: list[dict[str, Any]] = [
    {
        "id": uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        "code": "SUPERADMIN",
        "name": "Super Administrador",
        "description": "Acceso total y configuración de parámetros globales.",
    },
    {
        "id": uuid.UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"),
        "code": "ENCARGADO",
        "name": "Encargado del Negocio",
        "description": "Gestión de cotizaciones, overrides, aprobación de shows y reportes.",
    },
    {
        "id": uuid.UUID("c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33"),
        "code": "OPERADOR",
        "name": "Operador de Elenco / Campo",
        "description": "Confirmación de cobro in-situ y reporte de extensiones de show.",
    },
]

# --- Catálogo de paquetes base ---
PACKAGES: list[dict[str, Any]] = [
    {
        "name": "Hora Loca Básica",
        "service_category": "SHOW",
        "base_price": "450.00",
        "direct_cost": "250.00",
        "duration_minutes": 45,
    },
    {
        "name": "Hora Loca Medium",
        "service_category": "SHOW",
        "base_price": "750.00",
        "direct_cost": "400.00",
        "duration_minutes": 60,
    },
    {
        "name": "Hora Loca Premium",
        "service_category": "SHOW",
        "base_price": "1200.00",
        "direct_cost": "650.00",
        "duration_minutes": 60,
    },
    {
        "name": "Show Infantil Divertido",
        "service_category": "SHOW",
        "base_price": "650.00",
        "direct_cost": "350.00",
        "duration_minutes": 90,
    },
    {
        "name": "Paquete Baby Shower Especial",
        "service_category": "SHOW",
        "base_price": "550.00",
        "direct_cost": "300.00",
        "duration_minutes": 90,
    },
    {
        "name": "Servicio de DJ y Luces Pro",
        "service_category": "DJ",
        "base_price": "600.00",
        "direct_cost": "350.00",
        "duration_minutes": 240,
    },
    {
        "name": "Ambientación y Toldos Estándar",
        "service_category": "TENTS",
        "base_price": "900.00",
        "direct_cost": "450.00",
        "duration_minutes": 480,
    },
    {
        "name": "Combo Full Fiesta (Hora Loca + DJ)",
        "service_category": "SHOW",
        "base_price": "1300.00",
        "direct_cost": "700.00",
        "duration_minutes": 240,
    },
]

# --- Catálogo de temáticas ---
THEMES: list[dict[str, Any]] = [
    {
        "name": "Selva Salvaje (Safari)",
        "description": "Shows dinámicos con accesorios de safari y animales.",
    },
    {
        "name": "Neón Glow / Fluorescente",
        "description": "Luces ultravioleta, cotillón fluorescente y pintura facial neón.",
    },
    {
        "name": "Retro 80s & 90s",
        "description": "Música clásica bailable y vestimenta retro.",
    },
    {
        "name": "Infantil Superhéroes / Cuentos",
        "description": "Disfraces y dinámicas para público infantil.",
    },
    {
        "name": "Elegance Black & Gold",
        "description": "Temática sobria para 40 y 50 años o eventos corporativos.",
    },
]

# --- Catálogo de extras ---
EXTRAS: list[dict[str, Any]] = [
    {
        "name": "Muñeco Gorila Gigante",
        "sale_price": "250.00",
        "direct_cost": "120.00",
        "description": "Personaje inflable gigante estrella para el clímax de la Hora Loca.",
    },
    {
        "name": "Robot LED con Pistola de CO2",
        "sale_price": "350.00",
        "direct_cost": "180.00",
        "description": "Personaje con iluminación LED y disparos de humo frío.",
    },
    {
        "name": "Bailarín / Animador Adicional",
        "sale_price": "150.00",
        "direct_cost": "90.00",
        "description": "Personal extra para eventos con más de 100 invitados.",
    },
    {
        "name": "Cañón de Confeti / Ventilación",
        "sale_price": "120.00",
        "direct_cost": "50.00",
        "description": "Explosión de papel picado metalizado.",
    },
    {
        "name": "Hora Extra de DJ",
        "sale_price": "150.00",
        "direct_cost": "80.00",
        "description": "Extensión del servicio musical por hora adicional en vivo.",
    },
    {
        "name": "Media Hora Extra de Espera/Show",
        "sale_price": "100.00",
        "direct_cost": "60.00",
        "description": "Retraso o extensión solicitada por el cliente in-situ.",
    },
]

# --- Inventario inicial ---
INVENTORY_ITEMS: list[dict[str, Any]] = [
    {
        "name": "Toldo Estándar 3x3 m",
        "service_category": "TENTS",
        "total_stock": 10,
        "description": "Estructura con cobertura para eventos en exteriores.",
    },
    {
        "name": "Kit de Ambientación Estándar",
        "service_category": "DECORATION",
        "total_stock": 6,
        "description": "Telas, globos y elementos decorativos del paquete de ambientación.",
    },
]

# --- Inventario que consume cada paquete ---
PACKAGE_INVENTORY_LINKS: dict[str, list[tuple[str, int]]] = {
    "Ambientación y Toldos Estándar": [
        ("Toldo Estándar 3x3 m", 1),
        ("Kit de Ambientación Estándar", 1),
    ],
}


async def _get_or_create(
    session: AsyncSession,
    model: type[Any],
    defaults: dict[str, Any] | None = None,
    **filters: Any,
) -> tuple[Any, bool]:
    """Devuelve ``(instancia, creada)`` buscando por ``filters`` e insertando si falta."""

    result = await session.execute(select(model).filter_by(**filters))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    instance = model(**filters, **(defaults or {}))
    session.add(instance)
    await session.flush()
    return instance, True


async def seed(session: AsyncSession) -> dict[str, int]:
    """Siembra roles y catálogo. Devuelve el conteo de registros creados."""

    counts = {
        "roles": 0,
        "packages": 0,
        "themes": 0,
        "extras": 0,
        "inventory_items": 0,
        "package_inventory_items": 0,
    }

    for role in ROLES:
        _, created = await _get_or_create(
            session,
            Role,
            defaults={
                "id": role["id"],
                "name": role["name"],
                "description": role["description"],
            },
            code=role["code"],
        )
        counts["roles"] += int(created)

    for package in PACKAGES:
        _, created = await _get_or_create(
            session,
            PackageModel,
            defaults={
                "service_category": package["service_category"],
                "base_price": Decimal(package["base_price"]),
                "direct_cost": Decimal(package["direct_cost"]),
                "duration_minutes": package["duration_minutes"],
            },
            name=package["name"],
        )
        counts["packages"] += int(created)

    for theme in THEMES:
        _, created = await _get_or_create(
            session,
            ThemeModel,
            defaults={"description": theme["description"]},
            name=theme["name"],
        )
        counts["themes"] += int(created)

    for extra in EXTRAS:
        _, created = await _get_or_create(
            session,
            ExtraModel,
            defaults={
                "sale_price": Decimal(extra["sale_price"]),
                "direct_cost": Decimal(extra["direct_cost"]),
                "description": extra["description"],
            },
            name=extra["name"],
        )
        counts["extras"] += int(created)

    for item in INVENTORY_ITEMS:
        _, created = await _get_or_create(
            session,
            InventoryItemModel,
            defaults={
                "service_category": item["service_category"],
                "total_stock": item["total_stock"],
                "description": item["description"],
            },
            name=item["name"],
        )
        counts["inventory_items"] += int(created)

    for package_name, items in PACKAGE_INVENTORY_LINKS.items():
        package_obj, _ = await _get_or_create(session, PackageModel, name=package_name)
        for item_name, quantity in items:
            item_obj, _ = await _get_or_create(session, InventoryItemModel, name=item_name)
            _, created = await _get_or_create(
                session,
                PackageInventoryItemModel,
                defaults={"quantity": quantity},
                package_id=package_obj.id,
                inventory_item_id=item_obj.id,
            )
            counts["package_inventory_items"] += int(created)

    return counts


async def run_seed() -> dict[str, int]:
    """Abre una sesión, siembra y confirma la transacción."""

    async with get_sessionmaker()() as session:
        counts = await seed(session)
        await session.commit()
        return counts


def main() -> None:
    """Punto de entrada del comando de sembrado."""

    counts = asyncio.run(run_seed())
    created = ", ".join(f"{name}={value}" for name, value in counts.items())
    print(f"Seed completado (creados): {created}")


if __name__ == "__main__":
    main()
