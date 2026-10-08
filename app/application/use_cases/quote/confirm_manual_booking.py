"""Validación del adelanto → reserva de recursos → contrato emitido (PC-05)."""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from uuid import NAMESPACE_URL, UUID, uuid5
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

    async def execute(
        self,
        quote_id: UUID,
        user_id: UUID,
        *,
        approve_overbooking: bool = False,
        self_verification_reason: str | None = None,
        may_verify_own_receipt: bool = False,
    ) -> ManualBooking:
        if approve_overbooking and (
            not self_verification_reason or len(self_verification_reason.strip()) < 10
        ):
            raise ValidationError("La aprobación de sobrecupo requiere un motivo documentado")
        # El render no usa la conexión ni mantiene el candado de disponibilidad.
        preview = await self._store.get(quote_id)
        if preview is None:
            raise ResourceNotFoundError("Solicitud manual no encontrada")
        contract_id = uuid5(NAMESPACE_URL, f"eventpro:manual-contract:{quote_id}")
        number = "CTR-" + contract_id.hex[:20].upper()
        pdf = await self._render(preview, number) if preview.event_id is None else b""
        booking = await self._store.get(quote_id, lock=True)
        if booking is None:
            raise ResourceNotFoundError("Solicitud manual no encontrada")
        # Reintentos devuelven la misma reserva y contrato, sin duplicarlos.
        if booking.event_id is not None:
            if booking.contract_id is not None and booking.payment_status == "VERIFIED":
                return booking
            raise ValidationError("La reserva existente requiere revisión del encargado")
        if preview != booking:
            raise ResourceInUseError(
                "La solicitud cambió durante la revisión; vuelve a consultarla"
            )
        if booking.quote_status != "PAYMENT_STARTED":
            raise ValidationError("La cotización no está en estado PAYMENT_STARTED")
        if booking.expires_at is not None and booking.expires_at <= datetime.now(UTC):
            raise ValidationError("La cotización venció; requiere revisión antes de reservar")
        if booking.registered_by_user_id == user_id and (
            not may_verify_own_receipt
            or not self_verification_reason
            or len(self_verification_reason.strip()) < 10
        ):
            raise ValidationError(
                "Verificar un comprobante propio requiere una excepción supervisada"
            )
        if booking.payment_status not in ("PENDING_VERIFICATION", "REQUIRES_MANUAL_APPROVAL"):
            raise ValidationError("El pago no está pendiente de verificación")
        if booking.paid_amount != booking.advance_amount:
            raise ValidationError("El importe del pago no coincide con el adelanto cotizado")
        
        # --- VALIDACIÓN NUEVA ---
        if booking.event_date < date.today():
            raise ValidationError("No se puede confirmar un evento con fecha en el pasado.")
        # ------------------------

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
        if not availability.is_available and (
            not approve_overbooking
            or not availability.requires_manual_approval
            or availability.shortages
        ):
            return await self._store.require_approval(booking, user_id)
        if booking.payment_status == "REQUIRES_MANUAL_APPROVAL" and not approve_overbooking:
            raise ResourceInUseError(
                "El pago requiere aprobación explícita del sobrecupo o reembolso"
            )
        requirements = tuple(await self._catalog.get_inventory_requirements(package.id))
        event_id = uuid5(NAMESPACE_URL, f"eventpro:manual-event:{quote_id}")
        path = await self._documents.store(
            data=pdf, content_type="application/pdf", original_filename=number + ".pdf"
        )
        # Documento y reserva comparten la transacción: rollback elimina ambos;
        # no se borra un PDF durable ante un resultado de commit incierto.
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
            self_verification_reason,
        )