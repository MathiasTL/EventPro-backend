"""Creación real de cotizaciones; el llamador es dueño de la transacción."""

from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.application.dtos.availability_dto import AvailabilityRequest, AvailabilityStatus
from app.application.dtos.quote_dto import CreatedQuoteDTO, CreateQuoteInput, QuoteBreakdownDTO
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.client_repository_port import IClientRepositoryPort
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort
from app.application.ports.output.route_estimator_port import IRouteEstimatorPort
from app.domain.entities.quote import Quote, QuoteExtraLine, QuoteSource
from app.domain.exceptions.quote_exceptions import (
    AvailabilityAlternative,
    AvailabilityConflictError,
    ClientNotFoundError,
    RouteEstimationError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.services.financial_engine import FinancialEngine
from app.domain.value_objects.liquidation import ExtraCharge
from app.domain.value_objects.mobility import MobilityZone, RouteLocation
from app.domain.value_objects.money import Money


class CreateQuoteUseCase:
    def __init__(
        self,
        quotes: IQuoteRepositoryPort,
        clients: IClientRepositoryPort,
        catalog: ICatalogReadPort,
        availability: IAvailabilityPort,
        routes: IRouteEstimatorPort,
        financial: FinancialEngine,
        clock: IClockPort,
        origin: RouteLocation,
        zone_for_district: Callable[[str], MobilityZone],
        deadline_hours: int = 24,
    ) -> None:
        self._quotes = quotes
        self._clients = clients
        self._catalog = catalog
        self._availability = availability
        self._routes = routes
        self._financial = financial
        self._clock = clock
        self._origin = origin
        self._zone = zone_for_district
        self._deadline = deadline_hours

    async def execute(self, dto: CreateQuoteInput) -> CreatedQuoteDTO:
        now = self._clock.utcnow().astimezone(UTC)
        if dto.event_time.tzinfo is not None:
            raise ValidationError("Indica la hora local de Lima sin offset")
        starts_at = datetime.combine(dto.event_date, dto.event_time, ZoneInfo("America/Lima"))
        if starts_at <= now:
            raise ValidationError("El evento debe comenzar en una fecha y hora futura")
        if not isinstance(dto.source, QuoteSource):
            raise ValidationError("source debe ser WHATSAPP o MANUAL")
        destination = RouteLocation(
            address=dto.location_address, latitude=dto.latitude, longitude=dto.longitude
        )
        if not dto.location_district.strip():
            raise ValidationError("El distrito es obligatorio")
        client = await self._clients.get_by_id(dto.client_id) if dto.client_id else None
        if dto.client_id and client is None:
            raise ClientNotFoundError("Cliente no encontrado")
        package = await self._catalog.get_package(dto.package_id)
        if package is None or not package.is_active:
            raise ResourceNotFoundError("Paquete activo no encontrado")
        if dto.theme_id:
            theme = await self._catalog.get_theme(dto.theme_id)
            if theme is None or not theme.is_active:
                raise ResourceNotFoundError("Temática activa no encontrada")
            if not await self._catalog.are_themes_compatible(package.id, theme.id):
                raise ValidationError("La temática no es compatible con el paquete")
        if len({e.extra_id for e in dto.extras}) != len(dto.extras):
            raise ValidationError("No se puede repetir un extra")
        charges: list[ExtraCharge] = []
        lines: list[QuoteExtraLine] = []
        for item in dto.extras:
            extra = await self._catalog.get_extra(item.extra_id)
            if extra is None or not extra.is_active:
                raise ResourceNotFoundError("Extra activo no encontrado")
            charge = ExtraCharge(unit_price=Money(extra.sale_price), quantity=item.quantity)
            charges.append(charge)
            lines.append(
                QuoteExtraLine(item.extra_id, item.quantity, charge.unit_price, charge.subtotal)
            )
        result = await self._availability.check_availability(
            AvailabilityRequest(
                dto.event_date, dto.event_time, package.duration_minutes, package.id
            )
        )
        if not result.is_available:
            alternatives = []
            for days in range(1, 4):
                date = dto.event_date + timedelta(days=days)
                alternative = await self._availability.check_availability(
                    AvailabilityRequest(date, dto.event_time, package.duration_minutes, package.id)
                )
                if alternative.is_available:
                    alternatives.append(AvailabilityAlternative(date, dto.event_time))
            error = (
                AvailabilityConflictError
                if result.status is AvailabilityStatus.CONFLICT
                else SimultaneousThresholdExceededError
            )
            raise error(
                "El horario requiere otra fecha o revisión del encargado", alternatives=alternatives
            )
        estimate = None
        if not dto.client_provides_mobility:
            with suppress(RouteEstimationError):
                estimate = await self._routes.estimate(self._origin, destination)
        mobility = self._financial.resolve_mobility(
            client_provides_mobility=dto.client_provides_mobility,
            estimate=estimate,
            zone=self._zone(dto.location_district),
        )
        liquidation = self._financial.liquidate(
            package_price=Money(package.base_price),
            extras=charges,
            mobility_amount=mobility.final_amount,
        )
        if client is None:
            assert dto.client is not None
            client = await self._clients.get_or_create(
                dto.client.phone, dto.client.full_name, dni=dto.client.dni, ruc=dto.client.ruc
            )
        quote = Quote.create(
            client_id=client.id,
            source=dto.source,
            event_date=dto.event_date,
            event_time=dto.event_time,
            location_address=dto.location_address.strip(),
            location_district=dto.location_district.strip(),
            package_id=package.id,
            theme_id=dto.theme_id,
            client_provides_mobility=dto.client_provides_mobility,
            mobility=mobility,
            liquidation=liquidation,
            extras=lines,
            now=now,
            deadline_hours=self._deadline,
            latitude=dto.latitude,
            longitude=dto.longitude,
            observations=dto.observations,
        )
        await self._quotes.add(quote)
        return CreatedQuoteDTO(
            quote.id,
            client.id,
            quote.source,
            result.status,
            liquidation.services_subtotal.amount,
            mobility.distance_km,
            mobility.duration_minutes,
            mobility.final_amount.amount,
            liquidation.total_amount.amount,
            liquidation.advance_amount.amount,
            liquidation.pending_balance.amount,
            QuoteBreakdownDTO(
                liquidation.balance_services.amount, liquidation.balance_mobility.amount
            ),
            quote.status,
            quote.sent_at,
            quote.expires_at,
        )
