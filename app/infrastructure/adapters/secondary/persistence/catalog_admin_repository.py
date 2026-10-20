"""Repositorios de administración del catálogo y de elencos (E3).

Implementan ``ICatalogAdminPort`` e ``ICrewAdminPort`` sobre PostgreSQL. Las
invariantes de negocio ya fueron validadas por el dominio antes de llegar aquí.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.dtos.catalog_dto import (
    CrewDTO,
    ExtraDTO,
    InventoryItemDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.application.ports.output.catalog_admin_port import (
    ICatalogAdminPort,
    ICrewAdminPort,
)
from app.domain.entities.catalog import Crew, Extra, InventoryItem, Package, Theme
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
)
from app.domain.value_objects.service_category import ServiceCategory
from app.infrastructure.adapters.secondary.persistence.mappers import catalog_mapper
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    CrewModel,
    ExtraModel,
    InventoryItemModel,
    PackageInventoryItemModel,
    PackageModel,
    PackageThemeModel,
    ThemeModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)


def _crew_to_dto(crew: CrewModel) -> CrewDTO:
    return CrewDTO(
        id=crew.id,
        leader_name=crew.leader_name,
        phone=crew.phone,
        service_category=ServiceCategory(crew.service_category),
        user_id=crew.user_id,
        is_active=crew.is_active,
    )


class SqlAlchemyCatalogAdminRepository(ICatalogAdminPort):
    """Escritura del catálogo comercial."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_package(self, package: Package) -> PackageReadDTO:
        model = PackageModel(
            id=package.id,
            name=package.name,
            service_category=package.service_category.value,
            description=package.description,
            base_price=package.base_price.amount,
            direct_cost=package.direct_cost.amount,
            duration_minutes=package.duration_minutes,
            is_active=package.is_active,
            themes=[],
        )
        self._session.add(model)
        await self._session.flush()
        return catalog_mapper.package_to_dto(model)

    async def update_package(self, package: Package) -> PackageReadDTO:
        model = await self._get_package(package.id)
        model.name = package.name
        model.service_category = package.service_category.value
        model.description = package.description
        model.base_price = package.base_price.amount
        model.direct_cost = package.direct_cost.amount
        model.duration_minutes = package.duration_minutes
        await self._session.flush()
        return catalog_mapper.package_to_dto(model)

    async def deactivate_package(self, package_id: UUID) -> PackageReadDTO:
        model = await self._get_package(package_id)
        model.is_active = False
        await self._session.flush()
        return catalog_mapper.package_to_dto(model)

    async def set_package_inventory_items(
        self, package_id: UUID, items: Sequence[tuple[UUID, int]]
    ) -> Sequence[InventoryRequirementDTO]:
        await self._get_package(package_id)
        for inventory_item_id, _ in items:
            if await self._session.get(InventoryItemModel, inventory_item_id) is None:
                raise ResourceNotFoundError("Ítem de inventario no encontrado")

        await self._session.execute(
            delete(PackageInventoryItemModel).where(
                PackageInventoryItemModel.package_id == package_id
            )
        )
        for inventory_item_id, quantity in items:
            self._session.add(
                PackageInventoryItemModel(
                    package_id=package_id,
                    inventory_item_id=inventory_item_id,
                    quantity=quantity,
                )
            )
        await self._session.flush()
        return await self._requirement_rows(package_id)

    async def set_package_themes(
        self, package_id: UUID, theme_ids: Sequence[UUID]
    ) -> Sequence[ThemeDTO]:
        await self._get_package(package_id)
        for theme_id in theme_ids:
            if await self._session.get(ThemeModel, theme_id) is None:
                raise ResourceNotFoundError("Temática no encontrada")

        await self._session.execute(
            delete(PackageThemeModel).where(PackageThemeModel.package_id == package_id)
        )
        for theme_id in theme_ids:
            self._session.add(PackageThemeModel(package_id=package_id, theme_id=theme_id))
        await self._session.flush()

        if not theme_ids:
            return ()
        themes = (
            (await self._session.execute(select(ThemeModel).where(ThemeModel.id.in_(theme_ids))))
            .scalars()
            .all()
        )
        return tuple(catalog_mapper.theme_to_dto(theme) for theme in themes)

    async def create_theme(self, theme: Theme) -> ThemeDTO:
        await self._ensure_theme_name_available(theme.name, theme.id)
        model = ThemeModel(
            id=theme.id,
            name=theme.name,
            description=theme.description,
            is_active=theme.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return catalog_mapper.theme_to_dto(model)

    async def update_theme(self, theme: Theme) -> ThemeDTO:
        await self._ensure_theme_name_available(theme.name, theme.id)
        model = await self._session.get(ThemeModel, theme.id)
        if model is None:
            raise ResourceNotFoundError("Temática no encontrada")
        model.name = theme.name
        model.description = theme.description
        await self._session.flush()
        return catalog_mapper.theme_to_dto(model)

    async def deactivate_theme(self, theme_id: UUID) -> ThemeDTO:
        model = await self._session.get(ThemeModel, theme_id)
        if model is None:
            raise ResourceNotFoundError("Temática no encontrada")
        model.is_active = False
        await self._session.flush()
        return catalog_mapper.theme_to_dto(model)

    async def create_extra(self, extra: Extra) -> ExtraDTO:
        model = ExtraModel(
            id=extra.id,
            name=extra.name,
            description=extra.description,
            sale_price=extra.sale_price.amount,
            direct_cost=extra.direct_cost.amount,
            is_active=extra.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return catalog_mapper.extra_to_dto(model)

    async def update_extra(self, extra: Extra) -> ExtraDTO:
        model = await self._session.get(ExtraModel, extra.id)
        if model is None:
            raise ResourceNotFoundError("Extra no encontrado")
        model.name = extra.name
        model.description = extra.description
        model.sale_price = extra.sale_price.amount
        model.direct_cost = extra.direct_cost.amount
        await self._session.flush()
        return catalog_mapper.extra_to_dto(model)

    async def deactivate_extra(self, extra_id: UUID) -> ExtraDTO:
        model = await self._session.get(ExtraModel, extra_id)
        if model is None:
            raise ResourceNotFoundError("Extra no encontrado")
        model.is_active = False
        await self._session.flush()
        return catalog_mapper.extra_to_dto(model)

    async def create_inventory_item(self, item: InventoryItem) -> InventoryItemDTO:
        await self._ensure_inventory_name_available(item.name, item.id)
        model = InventoryItemModel(
            id=item.id,
            name=item.name,
            service_category=item.service_category.value,
            total_stock=item.total_stock,
            description=item.description,
            is_active=item.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return catalog_mapper.inventory_item_to_dto(model)

    async def update_inventory_item(self, item: InventoryItem) -> InventoryItemDTO:
        await self._ensure_inventory_name_available(item.name, item.id)
        model = await self._session.get(InventoryItemModel, item.id)
        if model is None:
            raise ResourceNotFoundError("Ítem de inventario no encontrado")
        model.name = item.name
        model.service_category = item.service_category.value
        model.total_stock = item.total_stock
        model.description = item.description
        await self._session.flush()
        return catalog_mapper.inventory_item_to_dto(model)

    async def deactivate_inventory_item(self, item_id: UUID) -> InventoryItemDTO:
        model = await self._session.get(InventoryItemModel, item_id)
        if model is None:
            raise ResourceNotFoundError("Ítem de inventario no encontrado")
        model.is_active = False
        await self._session.flush()
        return catalog_mapper.inventory_item_to_dto(model)

    async def count_active_package_usage(self, inventory_item_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(PackageInventoryItemModel)
            .join(PackageModel, PackageModel.id == PackageInventoryItemModel.package_id)
            .where(
                PackageInventoryItemModel.inventory_item_id == inventory_item_id,
                PackageModel.is_active.is_(True),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_future_reserved_units(self, inventory_item_id: UUID) -> int:
        stmt = select(func.coalesce(func.sum(InventoryReservationModel.quantity), 0)).where(
            InventoryReservationModel.inventory_item_id == inventory_item_id,
            InventoryReservationModel.status == "ACTIVE",
            InventoryReservationModel.ends_at > datetime.now(UTC),
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_package_direct_costs(self) -> dict[UUID, Decimal]:
        stmt = select(PackageModel.id, PackageModel.direct_cost)
        rows = (await self._session.execute(stmt)).all()
        return {row.id: row.direct_cost for row in rows}

    async def list_extra_direct_costs(self) -> dict[UUID, Decimal]:
        stmt = select(ExtraModel.id, ExtraModel.direct_cost)
        rows = (await self._session.execute(stmt)).all()
        return {row.id: row.direct_cost for row in rows}

    async def list_inventory_items(
        self, *, include_inactive: bool = False
    ) -> Sequence[InventoryItemDTO]:
        stmt = select(InventoryItemModel).order_by(InventoryItemModel.name)
        if not include_inactive:
            stmt = stmt.where(InventoryItemModel.is_active.is_(True))
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(catalog_mapper.inventory_item_to_dto(row) for row in rows)

    async def _get_package(self, package_id: UUID) -> PackageModel:
        model = await self._session.get(
            PackageModel, package_id, options=[selectinload(PackageModel.themes)]
        )
        if model is None:
            raise ResourceNotFoundError("Paquete no encontrado")
        return model

    async def _requirement_rows(self, package_id: UUID) -> Sequence[InventoryRequirementDTO]:
        stmt = (
            select(
                PackageInventoryItemModel.inventory_item_id,
                PackageInventoryItemModel.quantity,
                InventoryItemModel.name,
            )
            .join(
                InventoryItemModel,
                InventoryItemModel.id == PackageInventoryItemModel.inventory_item_id,
            )
            .where(PackageInventoryItemModel.package_id == package_id)
            .order_by(PackageInventoryItemModel.inventory_item_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return tuple(
            InventoryRequirementDTO(
                inventory_item_id=row.inventory_item_id,
                quantity=row.quantity,
                name=row.name,
            )
            for row in rows
        )

    async def _ensure_theme_name_available(self, name: str, theme_id: UUID) -> None:
        stmt = select(ThemeModel.id).where(ThemeModel.name == name, ThemeModel.id != theme_id)
        if (await self._session.execute(stmt)).scalar_one_or_none() is not None:
            raise DuplicateResourceError("Ya existe una temática con ese nombre")

    async def _ensure_inventory_name_available(self, name: str, item_id: UUID) -> None:
        stmt = select(InventoryItemModel.id).where(
            InventoryItemModel.name == name, InventoryItemModel.id != item_id
        )
        if (await self._session.execute(stmt)).scalar_one_or_none() is not None:
            raise DuplicateResourceError("Ya existe un ítem de inventario con ese nombre")


class SqlAlchemyCrewAdminRepository(ICrewAdminPort):
    """Gestión de elencos freelance."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_crews(self, *, include_inactive: bool = False) -> Sequence[CrewDTO]:
        stmt = select(CrewModel).order_by(CrewModel.leader_name)
        if not include_inactive:
            stmt = stmt.where(CrewModel.is_active.is_(True))
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(_crew_to_dto(row) for row in rows)

    async def get_crew(self, crew_id: UUID) -> CrewDTO | None:
        model = await self._session.get(CrewModel, crew_id)
        return _crew_to_dto(model) if model is not None else None

    async def find_crew_by_user(self, user_id: UUID) -> CrewDTO | None:
        stmt = select(CrewModel).where(CrewModel.user_id == user_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _crew_to_dto(model) if model is not None else None

    async def create_crew(self, crew: Crew) -> CrewDTO:
        model = CrewModel(
            id=crew.id,
            user_id=crew.user_id,
            leader_name=crew.leader_name,
            phone=crew.phone,
            service_category=crew.service_category.value,
            is_active=crew.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return _crew_to_dto(model)

    async def update_crew(self, crew: Crew) -> CrewDTO:
        model = await self._session.get(CrewModel, crew.id)
        if model is None:
            raise ResourceNotFoundError("Elenco no encontrado")
        model.user_id = crew.user_id
        model.leader_name = crew.leader_name
        model.phone = crew.phone
        model.service_category = crew.service_category.value
        model.is_active = crew.is_active
        await self._session.flush()
        return _crew_to_dto(model)
