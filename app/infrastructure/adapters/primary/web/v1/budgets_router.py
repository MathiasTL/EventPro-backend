"""Proceso de presupuesto administrativo con documento PDF final."""

import base64
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.application.dtos.budget_dto import BudgetInput
from app.application.ports.output.manual_booking_port import IBookingDocuments
from app.application.use_cases.quote.prepare_budget import PrepareBudgetUseCase
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.manual_booking_schemas import (
    BudgetLineResponse,
    BudgetRequest,
    BudgetResponse,
)
from app.infrastructure.adapters.secondary.persistence.database import get_session
from app.infrastructure.adapters.secondary.storage.booking_pdf import render_pdf
from app.infrastructure.di.containers import get_budget_documents, get_prepare_budget_use_case

router = APIRouter(prefix="/budgets", tags=["Presupuestos"])


@router.post("/prepare", response_model=BudgetResponse)
async def prepare_budget(
    payload: BudgetRequest,
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    use_case: Annotated[PrepareBudgetUseCase, Depends(get_prepare_budget_use_case)],
    documents: Annotated[IBookingDocuments, Depends(get_budget_documents)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BudgetResponse:
    from datetime import UTC

    try:
        result = await use_case.execute(
            BudgetInput(
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
            )
        )
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Solicitud inválida", str(exc)) from exc
    budget_id = uuid4()
    pdf = await run_in_threadpool(render_pdf, result, budget_id)
    await documents.store(
        data=pdf, content_type="application/pdf", original_filename=f"{budget_id}.pdf"
    )
    await session.commit()
    return BudgetResponse(
        budget_id=budget_id,
        generated_at=datetime.now(UTC),
        package_name=result.package_name,
        theme_name=result.theme_name,
        duration_minutes=result.duration_minutes,
        lines=[BudgetLineResponse(name=line.name, amount=line.amount) for line in result.lines],
        services_subtotal=result.services_subtotal,
        mobility_amount=result.mobility_amount,
        total_amount=result.total_amount,
        advance_amount=result.advance_amount,
        pending_balance=result.pending_balance,
        availability_status=result.availability.status,
        simultaneous_count=result.availability.simultaneous_count,
        pdf_base64=base64.b64encode(pdf).decode("ascii"),
    )


@router.get("/{budget_id}/document")
async def get_budget_document(
    budget_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    documents: Annotated[IBookingDocuments, Depends(get_budget_documents)],
) -> dict[str, str]:
    try:
        pdf = await documents.open(f"database/budgets/{budget_id}")
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    return {
        "filename": f"presupuesto-{budget_id}.pdf",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
    }
