"""Entrada manual de solicitud y comprobante; confirmación del encargado (PC-05)."""

import base64
import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.budget_dto import BudgetInput
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.manual_booking_port import (
    IBookingDocuments,
    IManualBookingStore,
    ManualBooking,
)
from app.application.use_cases.quote.confirm_manual_booking import ConfirmManualBookingUseCase
from app.application.use_cases.quote.refund_manual_booking import RefundManualBookingUseCase
from app.application.use_cases.quote.register_manual_booking import (
    RegisterManualBookingInput,
    RegisterManualBookingUseCase,
)
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.manual_booking_schemas import (
    BookingResponse,
    ConfirmRequest,
    ManualRequest,
    RefundRequest,
)
from app.infrastructure.adapters.secondary.persistence.database import get_session
from app.infrastructure.di.containers import (
    get_availability_port,
    get_booking_documents,
    get_booking_receipts,
    get_catalog_read_port,
    get_confirm_manual_booking_use_case,
    get_manual_booking_store,
    get_refund_manual_booking_use_case,
    get_register_manual_booking_use_case,
)

router = APIRouter(prefix="/manual-bookings", tags=["Reserva manual"])
Staff = Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))]
Session = Annotated[AsyncSession, Depends(get_session)]
Catalog = Annotated[ICatalogReadPort, Depends(get_catalog_read_port)]
Availability = Annotated[IAvailabilityPort, Depends(get_availability_port)]
Storage = Annotated[IBookingDocuments, Depends(get_booking_receipts)]
Documents = Annotated[IBookingDocuments, Depends(get_booking_documents)]
Store = Annotated[IManualBookingStore, Depends(get_manual_booking_store)]


def response(booking: ManualBooking) -> BookingResponse:
    return BookingResponse(
        quote_id=booking.quote_id,
        client_name=booking.client_name,
        phone=booking.phone,
        address=booking.address,
        district=booking.district,
        event_date=booking.event_date,
        start_time=booking.start_time,
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
        registered_by_user_id=booking.registered_by_user_id,
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
    http_response: Response,
    use_case: Annotated[
        RegisterManualBookingUseCase, Depends(get_register_manual_booking_use_case)
    ],
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
    try:
        data = await receipt_file.read(storage.max_bytes() + 1)
        canonical = payload.model_dump(mode="json", exclude={"quote_id"})
        canonical["extra_ids"] = sorted(canonical["extra_ids"])
        canonical["paid_amount"] = f"{payload.paid_amount:.2f}"
        canonical["manual_mobility_amount"] = f"{payload.manual_mobility_amount:.2f}"
        canonical["receipt_sha256"] = hashlib.sha256(data).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps(
                canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
        booking, created = await use_case.execute(
            RegisterManualBookingInput(
                quote_id=payload.quote_id,
                budget=BudgetInput(
                    payload.client_name,
                    payload.event_date,
                    payload.start_time,
                    payload.address,
                    payload.package_id,
                    payload.theme_id,
                    tuple(payload.extra_ids),
                    payload.client_provides_transport,
                    payload.manual_mobility_amount,
                    payload.mobility_override_reason,
                ),
                phone=payload.phone,
                district=payload.district,
                payment_method=payload.payment_method.value,
                paid_amount=str(payload.paid_amount),
                request_hash=request_hash,
                receipt=data,
                content_type=receipt_file.content_type or "",
                filename=receipt_file.filename or "receipt",
            ),
            context.user_id,
        )
        http_response.status_code = 201 if created else 200
        return response(booking)
    except (ValidationError, ResourceNotFoundError, ResourceInUseError) as exc:
        raise map_error(exc) from exc


@router.get("", response_model=list[BookingResponse])
async def recent_bookings(
    context: Staff,
    store: Store,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[BookingResponse]:
    return [response(row) for row in await store.list_recent(page=page, page_size=page_size)]


@router.post("/{quote_id}/confirm", response_model=BookingResponse)
async def confirm_booking(
    quote_id: UUID,
    payload: ConfirmRequest,
    context: Staff,
    use_case: Annotated[ConfirmManualBookingUseCase, Depends(get_confirm_manual_booking_use_case)],
) -> BookingResponse:
    if not payload.receipt_verified:
        raise ProblemError(
            422,
            "validation-error",
            "Revisión requerida",
            "El encargado debe verificar el comprobante antes de confirmar.",
        )
    if payload.approve_overbooking and not payload.override_reason:
        raise ProblemError(
            422,
            "validation-error",
            "Motivo requerido",
            "Documenta el motivo de aprobación del sobrecupo",
        )
    try:
        booking = await use_case.execute(
            quote_id,
            context.user_id,
            approve_overbooking=payload.approve_overbooking,
            self_verification_reason=payload.override_reason,
            may_verify_own_receipt=context.role is Role.SUPERADMIN,
        )
        return response(booking)
    except InvalidPaymentStateError as exc:
        raise ProblemError(409, exc.code, "Estado inválido", str(exc)) from exc
    except (ValidationError, ResourceNotFoundError, ResourceInUseError) as exc:
        raise map_error(exc) from exc


@router.get("/{quote_id}/contract")
async def download_contract(
    quote_id: UUID, context: Staff, store: Store, storage: Documents
) -> dict[str, str]:
    booking = await store.get(quote_id)
    if booking is None or booking.pdf_path is None:
        raise ProblemError(404, "not-found", "No encontrado", "Todavía no hay contrato emitido.")
    data = await storage.open(booking.pdf_path)
    return {
        "filename": (booking.contract_number or "contrato") + ".pdf",
        "pdf_base64": base64.b64encode(data).decode("ascii"),
    }


@router.post("/{quote_id}/refund", response_model=BookingResponse)
async def refund_booking(
    quote_id: UUID,
    payload: RefundRequest,
    context: Staff,
    use_case: Annotated[RefundManualBookingUseCase, Depends(get_refund_manual_booking_use_case)],
) -> BookingResponse:
    try:
        return response(
            await use_case.execute(
                quote_id,
                context.user_id,
                confirm=payload.action == "CONFIRM",
                reason=payload.reason,
            )
        )
    except InvalidPaymentStateError as exc:
        raise ProblemError(409, exc.code, "Estado inválido", str(exc)) from exc
    except (ValidationError, ResourceNotFoundError) as exc:
        raise map_error(exc) from exc
