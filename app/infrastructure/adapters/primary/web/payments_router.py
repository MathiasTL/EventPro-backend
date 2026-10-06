"""Routers HTTP del módulo de pagos (E5): US-11, US-12."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.payment_dto import (
    AuditPaymentDTO,
    CreateAdvancePaymentDTO,
    PaymentFilterDTO,
    RefundPaymentDTO,
    VerifyPaymentDTO,
)
from app.application.use_cases import payments as uc
from app.domain.entities.payment import (
    AuditStatus,
    PaymentConcept,
    PaymentMethod,
    ValidationStatus,
)
from app.domain.exceptions.resource_exceptions import (
    DomainError,
    ResourceNotFoundError,
    ValidationError,
)
from app.infrastructure.adapters.primary.web.auth import CurrentUser, require_role
from app.infrastructure.adapters.secondary.persistence.database import get_session
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_payment_repository import (  # noqa: E501
    SqlAlchemyPaymentRepository,
)
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalPaymentEvidenceStorage,
)

router = APIRouter(tags=["payments"])


async def get_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyPaymentRepository:
    return SqlAlchemyPaymentRepository(session)


def get_storage() -> LocalPaymentEvidenceStorage:
    return LocalPaymentEvidenceStorage()


RepoDep = Annotated[SqlAlchemyPaymentRepository, Depends(get_repo)]
StorageDep = Annotated[LocalPaymentEvidenceStorage, Depends(get_storage)]
EncargadoDep = Annotated[CurrentUser, Depends(require_role("ENCARGADO", "SUPERADMIN"))]


def _map_domain_error(exc: DomainError) -> HTTPException:
    if isinstance(exc, ResourceNotFoundError):
        return HTTPException(status_code=404, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})
    return HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.post("/payments/advance", status_code=status.HTTP_201_CREATED)
async def register_advance_payment(
    quote_id: Annotated[UUID, Form(...)],
    payment_method: Annotated[PaymentMethod, Form(...)],
    amount: Annotated[Decimal, Form(...)],
    receipt_file: Annotated[UploadFile, File(...)],
    user: EncargadoDep,
    repo: RepoDep,
    storage: StorageDep,
    transaction_reference: Annotated[str | None, Form()] = None,
) -> dict:
    try:
        data = await receipt_file.read()
        evidence_path = await storage.store(
            data=data,
            content_type=receipt_file.content_type or "",
            original_filename=receipt_file.filename or "receipt",
        )
        result = await uc.RegisterAdvancePaymentUseCase(repo).execute(
            CreateAdvancePaymentDTO(
                quote_id=quote_id,
                payment_method=payment_method,
                amount=amount,
                evidence_path=evidence_path,
                transaction_reference=transaction_reference,
            )
        )
        return {
            "payment_id": str(result.payment_id),
            "quote_id": str(result.quote_id),
            "concept": result.concept.value,
            "validation_status": result.validation_status.value,
            "message": result.message,
        }
    except DomainError as exc:
        raise _map_domain_error(exc) from exc


@router.get("/payments")
async def list_payments(
    user: EncargadoDep,
    repo: RepoDep,
    validation_status: Annotated[ValidationStatus | None, Query()] = None,
    concept: Annotated[PaymentConcept | None, Query()] = None,
    audit_status: Annotated[AuditStatus | None, Query()] = None,
    quote_id: Annotated[UUID | None, Query()] = None,
    event_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    try:
        result = await uc.ListPaymentsUseCase(repo).execute(
            PaymentFilterDTO(
                validation_status=validation_status,
                concept=concept,
                audit_status=audit_status,
                quote_id=quote_id,
                event_id=event_id,
                page=page,
                page_size=page_size,
            )
        )
        return {
            "items": [
                {
                    "payment_id": str(item.payment_id),
                    "quote_id": str(item.quote_id),
                    "event_id": str(item.event_id) if item.event_id else None,
                    "concept": item.concept.value,
                    "payment_method": item.payment_method.value,
                    "amount": float(item.amount),
                    "validation_status": item.validation_status.value,
                    "audit_status": item.audit_status.value if item.audit_status else None,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in result.items
            ],
            "page": result.page,
            "page_size": result.page_size,
            "total": result.total,
        }
    except DomainError as exc:
        raise _map_domain_error(exc) from exc


@router.get("/payments/{payment_id}")
async def get_payment(payment_id: UUID, user: EncargadoDep, repo: RepoDep) -> dict:
    try:
        dto = await uc.GetPaymentUseCase(repo).execute(payment_id)
        return {
            "payment_id": str(dto.payment_id),
            "quote_id": str(dto.quote_id),
            "event_id": str(dto.event_id) if dto.event_id else None,
            "concept": dto.concept.value,
            "payment_method": dto.payment_method.value,
            "amount": float(dto.amount),
            "transaction_reference": dto.transaction_reference,
            "validation_status": dto.validation_status.value,
            "rejection_reason": dto.rejection_reason,
            "verified_by_user_id": (
                str(dto.verified_by_user_id) if dto.verified_by_user_id else None
            ),
            "registered_by_user_id": (
                str(dto.registered_by_user_id) if dto.registered_by_user_id else None
            ),
            "audit_status": dto.audit_status.value if dto.audit_status else None,
            "audited_by_user_id": str(dto.audited_by_user_id) if dto.audited_by_user_id else None,
            "audited_at": dto.audited_at.isoformat() if dto.audited_at else None,
            "audit_notes": dto.audit_notes,
            "created_at": dto.created_at.isoformat() if dto.created_at else None,
        }
    except DomainError as exc:
        raise _map_domain_error(exc) from exc


@router.get("/payments/{payment_id}/evidence")
async def get_payment_evidence(
    payment_id: UUID, user: EncargadoDep, repo: RepoDep, storage: StorageDep
) -> Response:
    try:
        data = await uc.GetPaymentEvidenceUseCase(repo, storage).execute(payment_id)
        return Response(content=data, media_type="application/octet-stream")
    except DomainError as exc:
        raise _map_domain_error(exc) from exc


@router.patch("/payments/{payment_id}/verify")
async def verify_payment(payment_id: UUID, body: dict, user: EncargadoDep, repo: RepoDep) -> dict:
    try:
        dto = VerifyPaymentDTO(
            status=ValidationStatus(body.get("status", "")),
            rejection_reason=body.get("rejection_reason"),
        )
        result = await uc.VerifyPaymentUseCase(repo).execute(
            payment_id, dto, verified_by=user.user_id or UUID(int=0)
        )
        return {
            "payment_id": str(result.payment_id),
            "validation_status": result.validation_status.value,
            "event_created_id": str(result.event_created_id) if result.event_created_id else None,
            "contract_status": result.contract_status,
        }
    except (DomainError, ValueError) as exc:
        if isinstance(exc, DomainError):
            raise _map_domain_error(exc) from exc
        raise HTTPException(status_code=422, detail="validation-error") from exc


@router.patch("/payments/{payment_id}/audit")
async def audit_payment(payment_id: UUID, body: dict, user: EncargadoDep, repo: RepoDep) -> dict:
    try:
        dto = AuditPaymentDTO(
            audit_status=AuditStatus(body.get("audit_status", "")),
            audit_notes=body.get("audit_notes"),
        )
        result = await uc.AuditPaymentUseCase(repo).execute(
            payment_id, dto, audited_by=user.user_id or UUID(int=0)
        )
        return {
            "payment_id": str(result.payment_id),
            "audit_status": result.audit_status.value if result.audit_status else None,
            "audited_by_user_id": (
                str(result.audited_by_user_id) if result.audited_by_user_id else None
            ),
            "audited_at": result.audited_at.isoformat() if result.audited_at else None,
        }
    except (DomainError, ValueError) as exc:
        if isinstance(exc, DomainError):
            raise _map_domain_error(exc) from exc
        raise HTTPException(status_code=422, detail="validation-error") from exc


@router.patch("/payments/{payment_id}/refund")
async def refund_payment(payment_id: UUID, body: dict, user: EncargadoDep, repo: RepoDep) -> dict:
    try:
        dto = RefundPaymentDTO(
            refund_method=PaymentMethod(body.get("refund_method", "")),
            transaction_reference=body.get("transaction_reference"),
            notes=body.get("notes"),
        )
        result = await uc.RefundPaymentUseCase(repo).execute(payment_id, dto)
        return {
            "payment_id": str(result.payment_id),
            "validation_status": result.validation_status.value,
        }
    except (DomainError, ValueError) as exc:
        if isinstance(exc, DomainError):
            raise _map_domain_error(exc) from exc
        raise HTTPException(status_code=422, detail="validation-error") from exc
