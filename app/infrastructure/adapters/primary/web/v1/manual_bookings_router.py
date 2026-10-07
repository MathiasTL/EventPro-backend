"""Entrada manual de solicitud y comprobante; confirmación del encargado (PC-05)."""

import base64
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.manual_booking_port import ManualBooking
from app.application.use_cases.quote.confirm_manual_booking import ConfirmManualBookingUseCase
from app.application.use_cases.quote.prepare_budget import BudgetInput, PrepareBudgetUseCase
from app.domain.entities.payment import PaymentMethod
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.v1.budgets_router import BudgetRequest
from app.infrastructure.adapters.secondary.persistence.database import get_session
from app.infrastructure.adapters.secondary.persistence.manual_booking_repository import (
    SqlAlchemyManualBookingStore,
)
from app.infrastructure.adapters.secondary.storage.document_pdf import render_document
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)
from app.infrastructure.di.containers import (
    get_availability_port,
    get_catalog_read_port,
    get_evidence_storage,
)

router = APIRouter(prefix="/manual-bookings", tags=["Reserva manual"])
Staff = Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))]
Session = Annotated[AsyncSession, Depends(get_session)]
Catalog = Annotated[ICatalogReadPort, Depends(get_catalog_read_port)]
Availability = Annotated[IAvailabilityPort, Depends(get_availability_port)]
Storage = Annotated[LocalEvidenceStorage, Depends(get_evidence_storage)]


class ManualRequest(BudgetRequest):
    quote_id: UUID
    phone: str = Field(pattern=r"^\+?[0-9]{9,15}$")
    district: str = Field(min_length=2, max_length=80)
    payment_method: PaymentMethod
    paid_amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_verified: bool


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    quote_id: UUID
    client_name: str
    phone: str
    address: str
    district: str
    event_date: str
    start_time: str
    package_name: str
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    payment_id: UUID
    payment_status: str
    quote_status: str
    event_id: UUID | None
    contract_id: UUID | None
    contract_number: str | None


def response(booking: ManualBooking) -> BookingResponse:
    return BookingResponse(
        quote_id=booking.quote_id,
        client_name=booking.client_name,
        phone=booking.phone,
        address=booking.address,
        district=booking.district,
        event_date=booking.event_date.isoformat(),
        start_time=booking.start_time.isoformat(),
        package_name=booking.package_name,
        total_amount=booking.total_amount,
        advance_amount=booking.advance_amount,
        pending_balance=booking.pending_balance,
        payment_id=booking.payment_id,
        payment_status=booking.payment_status,
        quote_status=booking.quote_status,
        event_id=booking.event_id,
        contract_id=booking.contract_id,
        contract_number=booking.contract_number,
    )


async def contract_pdf(booking: ManualBooking, number: str) -> bytes:
    return await run_in_threadpool(
        render_document,
        "EventPro - Contrato de servicios",
        [
            f"Contrato N° {number} | Modo manual",
            f"Cliente: {booking.client_name} | Contacto: {booking.phone}",
            f"Fecha: {booking.event_date} | Inicio: {booking.start_time:%H:%M} (Lima)",
            f"Dirección: {booking.address} | Distrito: {booking.district}",
            f"Paquete: {booking.package_name} | Duración: {booking.duration_minutes} minutos",
            f"Temática: {booking.theme_name or 'Sin temática'}",
            *[f"Servicio: {line.name} - S/ {line.amount:.2f}" for line in booking.lines],
            f"Total servicios: S/ {booking.total_amount:.2f}",
            "Transporte de ida y vuelta provisto por el cliente. Movilidad: S/ 0.00.",
            f"Adelanto validado: S/ {booking.advance_amount:.2f} (10% de servicios)",
            f"Saldo de servicios pendiente: S/ {booking.pending_balance:.2f}. "
            "Movilidad pendiente: S/ 0.00.",
            "El cliente deberá cancelar el saldo antes de iniciar el servicio. "
            "El tiempo adicional requiere acuerdo y registro del cobro correspondiente.",
            "El adelanto validado registra la reserva del evento y del inventario requerido. "
            "El contrato está emitido y pendiente de firma del cliente.",
            "Este documento no contiene una firma electrónica ni un sello PAdES. "
            "La firma y el envío por WhatsApp son etapas posteriores.",
            "Firma del cliente: ____________________   Fecha: ____________________",
            "Firma del representante de EventPro: ____________________",
        ],
    )


def map_error(exc: ValidationError | ResourceInUseError | ResourceNotFoundError) -> ProblemError:
    status = (
        404
        if isinstance(exc, ResourceNotFoundError)
        else 409
        if isinstance(exc, ResourceInUseError)
        else 422
    )
    return ProblemError(status, exc.code, "No se pudo completar la reserva", str(exc))


@router.post("", response_model=BookingResponse, status_code=201)
async def register_manual_booking(
    context: Staff,
    session: Session,
    catalog: Catalog,
    availability: Availability,
    storage: Storage,
    payload_json: Annotated[str, Form(max_length=10000)],
    receipt_file: Annotated[UploadFile, File()],
) -> BookingResponse:
    try:
        payload = ManualRequest.model_validate_json(payload_json)
    except ValueError as exc:
        raise ProblemError(
            422,
            "validation-error",
            "Datos inválidos",
            "Revisa los datos del cliente, evento y pago.",
        ) from exc
    store = SqlAlchemyManualBookingStore(session)
    existing = await store.get(payload.quote_id, lock=True)
    if existing is not None:
        if existing.phone != payload.phone or existing.package_id != payload.package_id:
            raise ProblemError(
                409, "conflict", "Conflicto", "La referencia ya pertenece a otra solicitud."
            )
        return response(existing)
    try:
        budget = await PrepareBudgetUseCase(catalog, availability).execute(
            BudgetInput(
                payload.client_name,
                payload.event_date,
                payload.start_time,
                payload.address,
                payload.package_id,
                payload.theme_id,
                tuple(payload.extra_ids),
            )
        )
        if payload.paid_amount != budget.advance_amount:
            raise ValidationError(
                "El importe del comprobante debe coincidir con el adelanto calculado (10%)"
            )
        if not budget.availability.is_available:
            raise ResourceInUseError(
                "No hay disponibilidad automática para esta solicitud. "
                "Selecciona otra fecha antes de registrar el pago."
            )
        data = await receipt_file.read(storage.max_bytes() + 1)
        path = await storage.store(
            data=data,
            content_type=receipt_file.content_type or "",
            original_filename=receipt_file.filename or "receipt",
        )
        booking = await store.stage(
            payload.quote_id,
            budget,
            payload.phone,
            payload.district,
            payload.payment_method.value,
            path,
        )
        return response(booking)
    except (ValidationError, ResourceNotFoundError, ResourceInUseError) as exc:
        raise map_error(exc) from exc


@router.get("", response_model=list[BookingResponse])
async def recent_bookings(context: Staff, session: Session) -> list[BookingResponse]:
    return [response(row) for row in await SqlAlchemyManualBookingStore(session).list_recent()]


@router.post("/{quote_id}/confirm", response_model=BookingResponse)
async def confirm_booking(
    quote_id: UUID,
    payload: ConfirmRequest,
    context: Staff,
    session: Session,
    catalog: Catalog,
    availability: Availability,
    storage: Storage,
) -> BookingResponse:
    if not payload.receipt_verified:
        raise ProblemError(
            422,
            "validation-error",
            "Revisión requerida",
            "El encargado debe verificar el comprobante antes de confirmar.",
        )
    try:
        booking = await ConfirmManualBookingUseCase(
            SqlAlchemyManualBookingStore(session),
            catalog,
            availability,
            storage,
            contract_pdf,
        ).execute(quote_id, context.user_id)
        return response(booking)
    except (ValidationError, ResourceNotFoundError, ResourceInUseError) as exc:
        raise map_error(exc) from exc


@router.get("/{quote_id}/contract")
async def download_contract(
    quote_id: UUID, context: Staff, session: Session, storage: Storage
) -> dict[str, str]:
    booking = await SqlAlchemyManualBookingStore(session).get(quote_id)
    if booking is None or booking.pdf_path is None:
        raise ProblemError(404, "not-found", "No encontrado", "Todavía no hay contrato emitido.")
    data = await storage.open(booking.pdf_path)
    return {
        "filename": (booking.contract_number or "contrato") + ".pdf",
        "pdf_base64": base64.b64encode(data).decode("ascii"),
    }
