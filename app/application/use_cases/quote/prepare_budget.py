"""Presupuesto previo: catálogo real, RF-06/07 y disponibilidad RF-09.

No crea una cotización SENT ni reserva cupo: esos estados requieren el flujo
de envío y validación del adelanto descrito en RN-09.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.application.dtos.availability_dto import AvailabilityRequest
from app.application.dtos.budget_dto import BudgetInput, BudgetLine, BudgetResult
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.services.financial_engine import FinancialEngine
from app.domain.value_objects.liquidation import ExtraCharge
from app.domain.value_objects.mobility import MobilityTariff
from app.domain.value_objects.money import Money


class PrepareBudgetUseCase:
    def __init__(
        self, catalog: ICatalogReadPort, availability: IAvailabilityPort, advance_percent: int = 10
    ) -> None:
        self._catalog = catalog
        self._availability = availability
        if not 0 < advance_percent <= 100:
            raise ValueError("advance_percent debe estar entre 1 y 100")
        # La movilidad manual ya es un importe final auditado; no lleva margen adicional.
        self._financial = FinancialEngine(
            tariff=MobilityTariff(
                Money.zero(),
                Money.zero(),
                Money.zero(),
                Decimal(0),
                Money.zero(),
                Money.zero(),
                Money.zero(),
            ),
            advance_percent=advance_percent,
        )

    async def execute(self, request: BudgetInput) -> BudgetResult:
        if request.start_time.tzinfo is not None:
            raise ValidationError("Indica la hora local de Lima sin offset de zona horaria")

        if request.client_provides_transport:
            if request.manual_mobility_amount != 0:
                raise ValidationError("El transporte del cliente exonera movilidad")
        elif request.manual_mobility_amount <= 0 or not request.mobility_override_reason:
            raise ValidationError("La movilidad manual requiere importe positivo y motivo")
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
        liquidation = self._financial.liquidate(
            package_price=Money(package.base_price),
            extras=tuple(ExtraCharge(Money(line.amount), 1) for line in lines[1:]),
            mobility_amount=Money(request.manual_mobility_amount),
        )
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
            services_subtotal=liquidation.services_subtotal.amount,
            mobility_amount=Money(request.manual_mobility_amount).amount,
            total_amount=liquidation.total_amount.amount,
            advance_amount=liquidation.advance_amount.amount,
            pending_balance=liquidation.pending_balance.amount,
            availability=availability,
        )
