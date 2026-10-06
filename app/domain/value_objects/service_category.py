"""Enumeración compartida ``service_category``.

Es única para elencos, paquetes e inventario. ``inventory_items`` solo admite el
subconjunto ``DECORATION`` y ``TENTS``. Los valores son códigos en inglés
``UPPER_SNAKE_CASE`` usados tal cual en la base de datos y en los payloads de la API.
"""

from enum import StrEnum


class ServiceCategory(StrEnum):
    """Categoría de servicio (compartida por paquetes, elencos e inventario)."""

    SHOW = "SHOW"
    DJ = "DJ"
    DECORATION = "DECORATION"
    TENTS = "TENTS"


INVENTORY_SERVICE_CATEGORIES: frozenset[ServiceCategory] = frozenset(
    {ServiceCategory.DECORATION, ServiceCategory.TENTS}
)
"""Categorías que puede tener un ítem de inventario físico."""
