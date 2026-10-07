"""Presupuesto previo: catálogo real, RF-06/07 y disponibilidad RF-09.

No crea una cotización SENT ni reserva cupo: esos estados requieren el flujo
de envío y validación del adelanto descrito en RN-09.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.application.dtos.availability_dto import AvailabilityRequest, AvailabilityResult
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.money import Money


@dataclass(frozen=True)
class BudgetInput:
    client_name: str
    event_date: date
    start_time: time
    address: str
    package_id: UUID
    theme_id: UUID | None
    extra_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class BudgetLine:
    name: str
    amount: Decimal


@dataclass(frozen=True)
class BudgetResult:
    request: BudgetInput
    package_name: str
    theme_name: str | None
    duration_minutes: int
    lines: tuple[BudgetLine, ...]
    services_subtotal: Decimal
    mobility_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    availability: AvailabilityResult


class PrepareBudgetUseCase:
    def __init__(self, catalog: ICatalogReadPort, availability: IAvailabilityPort) -> None:
        self._catalog = catalog
        self._availability = availability

    async def execute(self, request: BudgetInput) -> BudgetResult:
        starts_at = datetime.combine(request.event_date, request.start_time).replace(
            tzinfo=ZoneInfo("America/Lima")
        )
        if starts_at <= datetime.now(ZoneInfo("America/Lima")):
            raise ValidationError("El evento debe comenzar en una fecha y hora futura")
        if len(set(request.extra_ids)) != len(request.extra_ids):
            raise ValidationError("No se puede seleccionar dos veces el mismo extra")
        package = await self._catalog.get_package(request.package_id)
        if package is None or not package.is_active:
            raise ResourceNotFoundError("Paquete activo no encontrado")
        theme_name = None
        if request.theme_id is not None:
            theme = await self._catalog.get_theme(request.theme_id)
            if theme is None or not theme.is_active:
                raise ResourceNotFoundError("Temática activa no encontrada")
            if not await self._catalog.are_themes_compatible(package.id, theme.id):
                raise ValidationError("La temática no es compatible con el paquete")
            theme_name = theme.name
        lines = [BudgetLine(package.name, package.base_price)]
        for extra_id in request.extra_ids:
            extra = await self._catalog.get_extra(extra_id)
            if extra is None or not extra.is_active:
                raise ResourceNotFoundError("Extra activo no encontrado")
            lines.append(BudgetLine(extra.name, extra.sale_price))
        subtotal = Money(sum((line.amount for line in lines), Decimal("0")))
        advance = subtotal * Decimal("0.10")
        availability = await self._availability.check_availability(
            AvailabilityRequest(
                request.event_date, request.start_time, package.duration_minutes, package.id
            )
        )
        return BudgetResult(
            request=request,
            package_name=package.name,
            theme_name=theme_name,
            duration_minutes=package.duration_minutes,
            lines=tuple(lines),
            services_subtotal=subtotal.amount,
            mobility_amount=Decimal("0.00"),
            total_amount=subtotal.amount,
            advance_amount=advance.amount,
            pending_balance=(subtotal - advance).amount,
            availability=availability,
        )
