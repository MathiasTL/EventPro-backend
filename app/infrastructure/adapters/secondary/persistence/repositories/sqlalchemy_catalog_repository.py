"""Repositorio de lectura del catálogo sobre PostgreSQL (SQLAlchemy 2.0 async).

Implementa ``ICatalogReadPort`` para los consumidores internos (bot de E1 y motor de
disponibilidad). Las relaciones ``themes`` e ``inventory_links`` del modelo paquete se
cargan con estrategia ``selectin`` (eager), compatible con sesiones asíncronas.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.catalog_dto import (
    ExtraDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.infrastructure.adapters.secondary.persistence.mappers import catalog_mapper
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    PackageInventoryItemModel,
    PackageModel,
    PackageThemeModel,
    ThemeModel,
)


class SqlAlchemyCatalogReadRepository(ICatalogReadPort):
    """Lectura del catálogo desde PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_packages(self, *, include_inactive: bool = False) -> Sequence[PackageReadDTO]:
        stmt = select(PackageModel).order_by(PackageModel.name)
        if not include_inactive:
            stmt = stmt.where(PackageModel.is_active.is_(True))
        result = await self._session.execute(stmt)
        return tuple(catalog_mapper.package_to_dto(package) for package in result.scalars().all())

    async def get_package(self, package_id: UUID) -> PackageReadDTO | None:
        package = await self._session.get(PackageModel, package_id)
        return catalog_mapper.package_to_dto(package) if package is not None else None

    async def list_themes(self, *, include_inactive: bool = False) -> Sequence[ThemeDTO]:
        stmt = select(ThemeModel).order_by(ThemeModel.name)
        if not include_inactive:
            stmt = stmt.where(ThemeModel.is_active.is_(True))
        result = await self._session.execute(stmt)
        return tuple(catalog_mapper.theme_to_dto(theme) for theme in result.scalars().all())

    async def get_theme(self, theme_id: UUID) -> ThemeDTO | None:
        theme = await self._session.get(ThemeModel, theme_id)
        return catalog_mapper.theme_to_dto(theme) if theme is not None else None

    async def list_extras(self, *, include_inactive: bool = False) -> Sequence[ExtraDTO]:
        stmt = select(ExtraModel).order_by(ExtraModel.name)
        if not include_inactive:
            stmt = stmt.where(ExtraModel.is_active.is_(True))
        result = await self._session.execute(stmt)
        return tuple(catalog_mapper.extra_to_dto(extra) for extra in result.scalars().all())

    async def get_extra(self, extra_id: UUID) -> ExtraDTO | None:
        extra = await self._session.get(ExtraModel, extra_id)
        return catalog_mapper.extra_to_dto(extra) if extra is not None else None

    async def get_inventory_requirements(
        self, package_id: UUID
    ) -> Sequence[InventoryRequirementDTO]:
        stmt = (
            select(PackageInventoryItemModel)
            .where(PackageInventoryItemModel.package_id == package_id)
            .order_by(PackageInventoryItemModel.inventory_item_id)
        )
        result = await self._session.execute(stmt)
        return tuple(catalog_mapper.requirement_to_dto(link) for link in result.scalars().all())

    async def are_themes_compatible(self, package_id: UUID, theme_id: UUID) -> bool:
        stmt = (
            select(PackageThemeModel.id)
            .where(
                PackageThemeModel.package_id == package_id,
                PackageThemeModel.theme_id == theme_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
