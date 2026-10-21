"""Gestión administrativa de contratos (RF-13). La firma pública pertenece a US-15."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.contract_dto import ContractFilters
from app.application.use_cases.contract.manage_contracts import ManageContracts
from app.domain.entities.contract import Contract, ContractStatus
from app.domain.exceptions.resource_exceptions import (
    DomainError,
    ResourceInUseError,
    ResourceNotFoundError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.contract_schemas import (
    ContractObservationsRequest,
    ContractPageResponse,
    ContractRead,
    IssueContractRequest,
    VoidContractRequest,
)
from app.infrastructure.adapters.secondary.persistence.database import get_contract_write_session
from app.infrastructure.di.containers import get_contract_use_case

router = APIRouter(prefix="/contracts", tags=["Contratos"])
Staff = Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))]
UseCase = Annotated[ManageContracts, Depends(get_contract_use_case)]
Transaction = Annotated[AsyncSession, Depends(get_contract_write_session, scope="function")]


def read(contract: Contract) -> ContractRead:
    return ContractRead(
        contract_id=contract.id,
        contract_number=contract.contract_number,
        event_id=contract.event_id,
        status=contract.status,
        is_manual_mode=contract.is_manual_mode,
        custom_clauses=contract.custom_clauses,
        signature_token_expires_at=contract.signature_token_expires_at,
        signed_at=contract.signed_at,
        signer_ip=contract.signer_ip,
        sealed_pdf_sha256=contract.sealed_pdf_sha256,
        is_timestamped=contract.is_timestamped,
        created_at=contract.created_at,
    )


def problem(exc: DomainError) -> ProblemError:
    status = (
        404
        if isinstance(exc, ResourceNotFoundError)
        else (409 if isinstance(exc, ResourceInUseError) else 422)
    )
    return ProblemError(status, exc.code, "Contrato no disponible", str(exc))


@router.get("", response_model=ContractPageResponse)
async def list_contracts(
    context: Staff,
    use_case: UseCase,
    status: ContractStatus | None = None,
    event_id: UUID | None = None,
    is_manual_mode: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ContractPageResponse:
    result = await use_case.list(ContractFilters(status, event_id, is_manual_mode, page, page_size))
    return ContractPageResponse(
        items=[read(c) for c in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post("", response_model=ContractRead)
async def issue_contract(
    payload: IssueContractRequest,
    context: Staff,
    transaction: Transaction,
    use_case: UseCase,
) -> ContractRead:
    """Emite o recupera el contrato vigente; permite recuperar eventos anteriores al despliegue."""
    try:
        return read(await use_case.issue_for_event(payload.event_id, context.user_id))
    except DomainError as exc:
        raise problem(exc) from exc


@router.get("/{contract_id}", response_model=ContractRead)
async def get_contract(contract_id: UUID, context: Staff, use_case: UseCase) -> ContractRead:
    try:
        return read(await use_case.get(contract_id))
    except DomainError as exc:
        raise problem(exc) from exc


@router.get("/{contract_id}/pdf", response_class=Response)
async def get_pdf(contract_id: UUID, context: Staff, use_case: UseCase) -> Response:
    try:
        content = await use_case.pdf(contract_id)
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{contract_id}.pdf"',
                "Cache-Control": "private, no-store",
            },
        )
    except DomainError as exc:
        raise problem(exc) from exc


@router.post("/{contract_id}/resend-link", response_model=ContractRead)
async def resend_link(
    contract_id: UUID,
    context: Staff,
    transaction: Transaction,
    use_case: UseCase,
) -> ContractRead:
    try:
        return read(await use_case.resend(contract_id, context.user_id))
    except DomainError as exc:
        raise problem(exc) from exc


@router.post("/{contract_id}/void", response_model=ContractRead)
async def void_contract(
    contract_id: UUID,
    payload: VoidContractRequest,
    context: Staff,
    transaction: Transaction,
    use_case: UseCase,
) -> ContractRead:
    try:
        return read(await use_case.void(contract_id, payload.reason, context.user_id))
    except DomainError as exc:
        raise problem(exc) from exc


@router.patch("/{contract_id}/observations", response_model=ContractRead)
async def update_observations(
    contract_id: UUID,
    payload: ContractObservationsRequest,
    context: Staff,
    transaction: Transaction,
    use_case: UseCase,
) -> ContractRead:
    """Regenera el PDF y rota el enlace antes de la firma; conserva notas y auditoría juntas."""
    try:
        return read(
            await use_case.update_observations(
                contract_id, payload.client_observations, context.user_id
            )
        )
    except DomainError as exc:
        raise problem(exc) from exc
