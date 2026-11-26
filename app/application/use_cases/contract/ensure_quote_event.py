"""Crea, al verificar el adelanto, el evento de una cotización del flujo conversacional."""

from uuid import NAMESPACE_URL, UUID, uuid5

from app.application.dtos.availability_dto import AvailabilityRequest
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.quote_event_port import IQuoteEventStore
from app.domain.entities.quote import Quote, QuoteStatus
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.time_window import TimeWindow


class EnsureQuoteEvent:
    def __init__(
        self,
        store: IQuoteEventStore,
        catalog: ICatalogReadPort,
        availability: IAvailabilityPort,
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._availability = availability

    async def ensure_event(self, quote_id: UUID, *, check_availability: bool = True) -> UUID | None:
        quote = await self._store.lock_quote(quote_id)
        if quote is None:
            raise ResourceNotFoundError("Cotización no encontrada")
        existing = await self._store.existing_event(quote_id)
        if existing is not None:
            event_id, _ = existing
            await self._convert(quote)
            return event_id
        if quote.status is not QuoteStatus.PAYMENT_STARTED:
            raise ResourceInUseError(
                "La cotización no admite crear el evento porque está "
                f"{quote.status.value}; indica el evento manualmente"
            )
        package = await self._catalog.get_package(quote.package_id)
        if package is None:
            raise ValidationError("El paquete de la cotización ya no existe")
        if check_availability:
            capacity = await self._availability.check_availability(
                AvailabilityRequest(
                    quote.event_date, quote.event_time, package.duration_minutes, quote.package_id
                )
            )
            if not capacity.is_available:
                return None
        requirements = tuple(await self._catalog.get_inventory_requirements(quote.package_id))
        window = TimeWindow.from_schedule(
            quote.event_date, quote.event_time, package.duration_minutes
        )
        event_id = uuid5(NAMESPACE_URL, f"eventpro:quote-event:{quote_id}")
        await self._store.add_event(quote, event_id, window, requirements)
        await self._convert(quote)
        return event_id

    async def _convert(self, quote: Quote) -> None:
        if quote.status is QuoteStatus.PAYMENT_STARTED:
            quote.convert()
            await self._store.save_quote(quote)
