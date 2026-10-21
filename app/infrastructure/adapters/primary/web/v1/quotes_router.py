"""Cotizaciones reales: alta, consulta y listado (Brenis, spec 08)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import (
    CreatedQuoteDTO,
    ListQuotesFilter,
    QuoteDetailDTO,
    QuoteListItemDTO,
)
from app.application.ports.input.quote_create_port import ICreateQuotePort
from app.application.ports.input.quote_read_port import IGetQuotePort, IListQuotesPort
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import (
    AvailabilityConflictError,
    ClientNotFoundError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError, quote_error_to_problem
from app.infrastructure.adapters.primary.web.schemas.quote_schemas import CreateQuoteRequest
from app.infrastructure.di import containers

router = APIRouter(prefix="/quotes", tags=["Cotizaciones"])
Allowed = Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))]


@router.post("", response_model=CreatedQuoteDTO, status_code=201)
async def create_quote(
    payload: CreateQuoteRequest,
    context: Allowed,
    use_case: Annotated[ICreateQuotePort, Depends(containers.get_create_quote_use_case)],
) -> CreatedQuoteDTO:
    try:
        return await use_case.execute(payload.to_input())
    except (
        AvailabilityConflictError,
        SimultaneousThresholdExceededError,
        ClientNotFoundError,
        ValidationError,
    ) as exc:
        raise quote_error_to_problem(exc) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc


@router.get("", response_model=PageDTO[QuoteListItemDTO])
async def list_quotes(
    context: Allowed,
    use_case: Annotated[IListQuotesPort, Depends(containers.get_list_quotes_use_case)],
    status: QuoteStatus | None = None,
    client_id: UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageDTO[QuoteListItemDTO]:
    try:
        return await use_case.execute(
            ListQuotesFilter(status, client_id, from_date, to_date, page, page_size)
        )
    except ValidationError as exc:
        raise quote_error_to_problem(exc) from exc


@router.get("/{quote_id}", response_model=QuoteDetailDTO)
async def get_quote(
    quote_id: UUID,
    context: Allowed,
    use_case: Annotated[IGetQuotePort, Depends(containers.get_quote_use_case)],
) -> QuoteDetailDTO:
    try:
        return await use_case.execute(quote_id)
    except QuoteNotFoundError as exc:
        raise quote_error_to_problem(exc) from exc
