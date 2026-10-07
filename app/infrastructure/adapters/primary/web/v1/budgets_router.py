"""Proceso de presupuesto administrativo con documento PDF final."""

import base64
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.application.dtos.availability_dto import AvailabilityStatus
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.use_cases.quote.prepare_budget import (
    BudgetInput,
    BudgetResult,
    PrepareBudgetUseCase,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.di.containers import get_availability_port, get_catalog_read_port

router = APIRouter(prefix="/budgets", tags=["Presupuestos"])


class BudgetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_name: str = Field(min_length=2, max_length=120)
    event_date: date
    start_time: time
    address: str = Field(min_length=5, max_length=250)
    package_id: UUID
    theme_id: UUID | None = None
    extra_ids: list[UUID] = Field(default_factory=list, max_length=30)
    # Primera entrega: exoneración RF-06, sin depender de una API Maps configurada.
    client_provides_transport: Literal[True]


class BudgetLineResponse(BaseModel):
    name: str
    amount: Decimal


class BudgetResponse(BaseModel):
    budget_id: UUID
    generated_at: datetime
    package_name: str
    theme_name: str | None
    duration_minutes: int
    lines: list[BudgetLineResponse]
    services_subtotal: Decimal
    mobility_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal
    pending_balance: Decimal
    availability_status: AvailabilityStatus
    simultaneous_count: int
    pdf_base64: str


def render_pdf(result: BudgetResult, budget_id: UUID) -> bytes:
    from app.infrastructure.adapters.secondary.storage.document_pdf import render_document

    return render_document(
        "EventPro - Presupuesto",
        [
            f"Referencia: {budget_id}",
            f"Cliente: {result.request.client_name}",
            f"Evento: {result.request.event_date} {result.request.start_time:%H:%M} (Lima), "
            f"{result.duration_minutes} minutos",
            f"Dirección: {result.request.address}",
            f"Temática: {result.theme_name or 'Sin temática'}",
            *[f"{line.name}: S/ {line.amount:.2f}" for line in result.lines],
            f"Servicios: S/ {result.services_subtotal:.2f} | "
            "Movilidad: S/ 0.00 (transporte del cliente)",
            f"Total: S/ {result.total_amount:.2f}",
            f"Adelanto requerido (10%): S/ {result.advance_amount:.2f} | "
            f"Saldo: S/ {result.pending_balance:.2f}",
            f"Disponibilidad: {result.availability.status.value}",
            "Presupuesto previo. No acredita pago ni reserva fecha o recursos. "
            "La disponibilidad se revalida al confirmar el adelanto. No es un contrato.",
        ],
    )


@router.post("/prepare", response_model=BudgetResponse)
async def prepare_budget(
    payload: BudgetRequest,
    context: Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))],
    catalog: Annotated[ICatalogReadPort, Depends(get_catalog_read_port)],
    availability: Annotated[IAvailabilityPort, Depends(get_availability_port)],
) -> BudgetResponse:
    from datetime import UTC

    try:
        result = await PrepareBudgetUseCase(catalog, availability).execute(
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
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Solicitud inválida", str(exc)) from exc
    budget_id = uuid4()
    pdf = await run_in_threadpool(render_pdf, result, budget_id)
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
