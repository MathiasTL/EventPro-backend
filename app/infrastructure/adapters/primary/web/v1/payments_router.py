"""Router HTTP del módulo de pagos (US-11/US-12)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, Query, Response, UploadFile

from app.application.dtos.payment_dto import (
    AuditPaymentInput,
    CreateAdvancePaymentInput,
    PaymentFilters,
    VerifyPaymentInput,
)
from app.application.use_cases.payment.audit_payment import AuditPaymentUseCase
from app.application.use_cases.payment.get_payment import GetPaymentUseCase
from app.application.use_cases.payment.get_payment_evidence import GetPaymentEvidenceUseCase
from app.application.use_cases.payment.list_payments import ListPaymentsUseCase
from app.application.use_cases.payment.refund_payment import RefundPaymentUseCase
from app.application.use_cases.payment.register_advance_payment import RegisterAdvancePaymentUseCase
from app.application.use_cases.payment.verify_payment import VerifyPaymentUseCase
from app.domain.entities.payment import (
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.exceptions.storage_exceptions import EvidenceValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.payment_schemas import (
    PaymentAuditRequest,
    PaymentAuditResponse,
    PaymentCreateResponse,
    PaymentPageResponse,
    PaymentReadResponse,
    PaymentRefundRequest,
    PaymentRefundResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
)
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)
from app.infrastructure.di import containers

router = APIRouter(prefix="/payments", tags=["Pagos"])


def _map_validation(exc: ValidationError) -> ProblemError:
    return ProblemError(422, "validation-error", "Error de validación", str(exc))


@router.post("/advance", response_model=PaymentCreateResponse, status_code=201)
async def register_advance_payment(
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[
        RegisterAdvancePaymentUseCase, Depends(containers.get_register_advance_payment_use_case)
    ],
    storage: Annotated[LocalEvidenceStorage, Depends(containers.get_evidence_storage)],
    quote_id: Annotated[UUID, Form(...)],
    payment_method: Annotated[PaymentMethod, Form(...)],
    amount: Annotated[Decimal, Form(...)],
    receipt_file: Annotated[UploadFile, File(...)],
    transaction_reference: Annotated[str | None, Form()] = None,
) -> PaymentCreateResponse:
    """Registra la captura del adelanto y la deja en PENDING_VERIFICATION."""
    try:
        data = await receipt_file.read()
        evidence_path = await storage.store(
            data=data,
            content_type=receipt_file.content_type or "",
            original_filename=receipt_file.filename or "receipt",
        )
        result = await use_case.execute(
            CreateAdvancePaymentInput(
                quote_id=quote_id,
                payment_method=payment_method,
                amount=amount,
                evidence_path=evidence_path,
                transaction_reference=transaction_reference,
            )
        )
        return PaymentCreateResponse.model_validate(result)
    except ValidationError as exc:
        if isinstance(exc, EvidenceValidationError):
            raise ProblemError(422, "invalid-file", "Comprobante inválido", str(exc)) from exc
        raise _map_validation(exc) from exc
    except ResourceInUseError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc


@router.get("", response_model=PaymentPageResponse)
async def list_payments(
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[ListPaymentsUseCase, Depends(containers.get_list_payments_use_case)],
    validation_status: Annotated[PaymentValidationStatus | None, Query()] = None,
    concept: Annotated[PaymentConcept | None, Query()] = None,
    audit_status: Annotated[PaymentAuditStatus | None, Query()] = None,
    quote_id: Annotated[UUID | None, Query()] = None,
    event_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[datetime | None, Query()] = None,
    to_date: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaymentPageResponse:
    try:
        filters = PaymentFilters(
            validation_status=validation_status,
            concept=concept,
            audit_status=audit_status,
            quote_id=quote_id,
            event_id=event_id,
            from_date=from_date,
            to_date=to_date,
            page=page,
            page_size=page_size,
        )
        result = await use_case.execute(filters)
        return PaymentPageResponse(
            items=[PaymentReadResponse.model_validate(item) for item in result.items],
            page=result.page,
            page_size=result.page_size,
            total=result.total,
        )
    except ValidationError as exc:
        raise _map_validation(exc) from exc


@router.get("/{payment_id}", response_model=PaymentReadResponse)
async def get_payment(
    payment_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[GetPaymentUseCase, Depends(containers.get_get_payment_use_case)],
) -> PaymentReadResponse:
    try:
        result = await use_case.execute(payment_id)
        return PaymentReadResponse.model_validate(result)
    except ResourceNotFoundError as exc:
        raise ProblemError(404, exc.code, "No encontrado", str(exc)) from exc


@router.get("/{payment_id}/evidence")
async def get_payment_evidence(
    payment_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[
        GetPaymentEvidenceUseCase, Depends(containers.get_get_payment_evidence_use_case)
    ],
) -> Response:
    try:
        data = await use_case.execute(payment_id)
        return Response(content=data, media_type="application/octet-stream")
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, exc.code, "No encontrado", str(exc)) from exc


@router.patch("/{payment_id}/verify", response_model=PaymentVerifyResponse)
async def verify_payment(
    payment_id: UUID,
    payload: Annotated[PaymentVerifyRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[VerifyPaymentUseCase, Depends(containers.get_verify_payment_use_case)],
) -> PaymentVerifyResponse:
    try:
        result = await use_case.execute(
            VerifyPaymentInput(
                payment_id=payment_id,
                action=payload.status,
                verified_by_user_id=context.user_id,
                event_id=payload.event_id,
                rejection_reason=payload.rejection_reason,
            )
        )
        return PaymentVerifyResponse.model_validate(result)
    except ResourceNotFoundError as exc:
        raise ProblemError(404, exc.code, "No encontrado", str(exc)) from exc
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except InvalidPaymentStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc


@router.patch("/{payment_id}/audit", response_model=PaymentAuditResponse)
async def audit_payment(
    payment_id: UUID,
    payload: Annotated[PaymentAuditRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[AuditPaymentUseCase, Depends(containers.get_audit_payment_use_case)],
) -> PaymentAuditResponse:
    try:
        result = await use_case.execute(
            AuditPaymentInput(
                payment_id=payment_id,
                audited_by_user_id=context.user_id,
                audit_status=payload.audit_status,
                audit_notes=payload.audit_notes,
            )
        )
        return PaymentAuditResponse.model_validate(result)
    except ResourceNotFoundError as exc:
        raise ProblemError(404, exc.code, "No encontrado", str(exc)) from exc
    except ValidationError as exc:
        raise _map_validation(exc) from exc
    except InvalidPaymentStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc


@router.patch("/{payment_id}/refund", response_model=PaymentRefundResponse)
async def refund_payment(
    payment_id: UUID,
    payload: Annotated[PaymentRefundRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[RefundPaymentUseCase, Depends(containers.get_refund_payment_use_case)],
) -> PaymentRefundResponse:
    try:
        result = await use_case.execute(payment_id)
        return PaymentRefundResponse.model_validate(result)
    except ResourceNotFoundError as exc:
        raise ProblemError(404, exc.code, "No encontrado", str(exc)) from exc
    except InvalidPaymentStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
