"""Validación del adelanto → reserva de recursos → contrato emitido (PC-05)."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.application.dtos.availability_dto import AvailabilityRequest
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.manual_booking_port import (
    IBookingDocuments,
    IManualBookingStore,
    ManualBooking,
)
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.time_window import TimeWindow


class ConfirmManualBookingUseCase:
    def __init__(
        self,
        store: IManualBookingStore,
        catalog: ICatalogReadPort,
        availability: IAvailabilityPort,
        documents: IBookingDocuments,
        render_contract: Callable[[ManualBooking, str], Awaitable[bytes]],
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._availability = availability
        self._documents = documents
        self._render = render_contract

    async def execute(self, quote_id: UUID, user_id: UUID) -> ManualBooking:
        booking = await self._store.get(quote_id, lock=True)
        if booking is None:
            raise ResourceNotFoundError("Solicitud manual no encontrada")
        # Reintentos devuelven la misma reserva y contrato, sin duplicarlos.
        if booking.event_id is not None:
            if booking.contract_id is not None and booking.payment_status == "VERIFIED":
                return booking
            raise ValidationError("La reserva existente requiere revisión del encargado")
        if booking.payment_status != "PENDING_VERIFICATION":
            raise ValidationError("El pago no está pendiente de verificación")
        if booking.paid_amount != booking.advance_amount:
            raise ValidationError("El importe del pago no coincide con el adelanto cotizado")
        starts_at = datetime.combine(booking.event_date, booking.start_time).replace(
            tzinfo=ZoneInfo("America/Lima")
        )
        if starts_at <= datetime.now(ZoneInfo("America/Lima")):
            raise ValidationError("No se puede reservar un evento en el pasado")
        package = await self._catalog.get_package(booking.package_id)
        if package is None or not package.is_active:
            raise ResourceNotFoundError("El paquete ya no está activo")
        availability = await self._availability.check_availability(
            AvailabilityRequest(
                booking.event_date, booking.start_time, package.duration_minutes, package.id
            )
        )
        if not availability.is_available:
            raise ResourceInUseError(
                "No se puede reservar automáticamente: inventario insuficiente o sobrecupo. "
                "El comprobante continúa pendiente; revisa otra fecha con el cliente."
            )
        requirements = tuple(await self._catalog.get_inventory_requirements(package.id))
        event_id, contract_id = uuid4(), uuid4()
        number = "CTR-" + contract_id.hex[:20].upper()
        pdf = await self._render(booking, number)
        path = await self._documents.store(
            data=pdf, content_type="application/pdf", original_filename=number + ".pdf"
        )
        try:
            return await self._store.finalize(
                booking,
                user_id,
                event_id,
                contract_id,
                number,
                path,
                TimeWindow.from_schedule(
                    booking.event_date, booking.start_time, package.duration_minutes
                ),
                requirements,
            )
        except BaseException:
            await self._documents.delete(path)
            raise
