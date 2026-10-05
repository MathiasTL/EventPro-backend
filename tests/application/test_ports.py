"""Prueba de contrato de los puertos de salida de E3.

Define implementaciones falsas en memoria que satisfacen ``ICatalogReadPort`` e
``IAvailabilityPort``. Sirven de referencia para E1/E6 y garantizan que los puertos
son implementables y usables sin infraestructura.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.dtos.availability_dto import (
    AvailabilityRequest,
    AvailabilityResult,
    AvailabilityStatus,
    CrewTransitRequest,
    CrewTransitResult,
    InventoryShortageDTO,
)
from app.application.dtos.catalog_dto import (
    ExtraDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.domain.value_objects.service_category import ServiceCategory


class InMemoryCatalogReadPort(ICatalogReadPort):
    """Implementación en memoria de referencia para el puerto de catálogo."""

    def __init__(
        self,
        packages: Sequence[PackageReadDTO] = (),
        themes: Sequence[ThemeDTO] = (),
        extras: Sequence[ExtraDTO] = (),
        requirements: dict[UUID, tuple[InventoryRequirementDTO, ...]] | None = None,
        compatibility: set[tuple[UUID, UUID]] | None = None,
    ) -> None:
        self._packages = {package.id: package for package in packages}
        self._themes = {theme.id: theme for theme in themes}
        self._extras = {extra.id: extra for extra in extras}
        self._requirements = requirements or {}
        self._compatibility = compatibility or set()

    async def list_packages(self, *, include_inactive: bool = False) -> Sequence[PackageReadDTO]:
        return tuple(
            package for package in self._packages.values() if include_inactive or package.is_active
        )

    async def get_package(self, package_id: UUID) -> PackageReadDTO | None:
        return self._packages.get(package_id)

    async def list_themes(self, *, include_inactive: bool = False) -> Sequence[ThemeDTO]:
        return tuple(
            theme for theme in self._themes.values() if include_inactive or theme.is_active
        )

    async def get_theme(self, theme_id: UUID) -> ThemeDTO | None:
        return self._themes.get(theme_id)

    async def list_extras(self, *, include_inactive: bool = False) -> Sequence[ExtraDTO]:
        return tuple(
            extra for extra in self._extras.values() if include_inactive or extra.is_active
        )

    async def get_extra(self, extra_id: UUID) -> ExtraDTO | None:
        return self._extras.get(extra_id)

    async def get_inventory_requirements(
        self, package_id: UUID
    ) -> Sequence[InventoryRequirementDTO]:
        return self._requirements.get(package_id, ())

    async def are_themes_compatible(self, package_id: UUID, theme_id: UUID) -> bool:
        return (package_id, theme_id) in self._compatibility


class FakeAvailabilityPort(IAvailabilityPort):
    """Implementación de referencia que devuelve resultados prefijados."""

    def __init__(self, result: AvailabilityResult, transit_result: CrewTransitResult) -> None:
        self._result = result
        self._transit_result = transit_result

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        return self._result

    async def check_crew_transit(self, request: CrewTransitRequest) -> CrewTransitResult:
        return self._transit_result


def _package(theme_id: UUID) -> PackageReadDTO:
    return PackageReadDTO(
        id=uuid4(),
        name="Hora Loca Medium",
        service_category=ServiceCategory.SHOW,
        base_price=Decimal("750.00"),
        duration_minutes=60,
        compatible_themes=(ThemeDTO(id=theme_id, name="Selva"),),
    )


def test_ports_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        ICatalogReadPort()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        IAvailabilityPort()  # type: ignore[abstract]


def test_catalog_read_port_contract() -> None:
    available_theme = ThemeDTO(id=uuid4(), name="Selva")
    inactive_theme = ThemeDTO(id=uuid4(), name="Antigua", is_active=False)
    package = _package(available_theme.id)
    extra = ExtraDTO(id=uuid4(), name="Gorila", sale_price=Decimal("250.00"))
    requirement = InventoryRequirementDTO(
        inventory_item_id=uuid4(), quantity=1, name="Toldo Estándar 3x3 m"
    )
    port = InMemoryCatalogReadPort(
        packages=[package],
        themes=[available_theme, inactive_theme],
        extras=[extra],
        requirements={package.id: (requirement,)},
        compatibility={(package.id, available_theme.id)},
    )

    async def _exercise() -> None:
        assert await port.list_packages() == (package,)
        assert await port.get_package(package.id) == package
        assert await port.get_package(uuid4()) is None
        assert await port.list_themes() == (available_theme,)
        assert len(await port.list_themes(include_inactive=True)) == 2
        assert await port.get_theme(available_theme.id) == available_theme
        assert await port.list_extras() == (extra,)
        assert await port.get_extra(extra.id) == extra
        assert await port.get_inventory_requirements(package.id) == (requirement,)
        assert await port.get_inventory_requirements(uuid4()) == ()
        assert await port.are_themes_compatible(package.id, available_theme.id)
        assert not await port.are_themes_compatible(package.id, inactive_theme.id)

    asyncio.run(_exercise())


def test_availability_status_helpers() -> None:
    available = AvailabilityResult(status=AvailabilityStatus.AVAILABLE)
    assert available.is_available
    assert not available.requires_manual_approval

    manual = AvailabilityResult(
        status=AvailabilityStatus.REQUIRES_MANUAL_APPROVAL, simultaneous_count=4
    )
    assert not manual.is_available
    assert manual.requires_manual_approval

    shortage = InventoryShortageDTO(inventory_item_id=uuid4(), requested=2, available=1)
    conflict = AvailabilityResult(status=AvailabilityStatus.CONFLICT, shortages=(shortage,))
    assert conflict.shortages == (shortage,)
    assert not conflict.is_available


def test_availability_port_contract() -> None:
    result = AvailabilityResult(status=AvailabilityStatus.AVAILABLE, simultaneous_count=2)
    transit = CrewTransitResult(feasible=True, required_minutes=105, available_gap_minutes=120)
    port = FakeAvailabilityPort(result, transit)
    start = datetime(2026, 12, 24, 19, 0)

    async def _exercise() -> None:
        request = AvailabilityRequest(
            event_date=date(2026, 12, 24),
            start_time=time(20, 0),
            duration_minutes=60,
            package_id=uuid4(),
        )
        assert await port.check_availability(request) is result

        transit_request = CrewTransitRequest(
            crew_id=uuid4(),
            previous_end=start,
            candidate_start=start,
            transit_minutes=75,
        )
        assert await port.check_crew_transit(transit_request) is transit

    asyncio.run(_exercise())
