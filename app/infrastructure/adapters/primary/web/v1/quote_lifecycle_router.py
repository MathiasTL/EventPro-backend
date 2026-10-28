"""Acciones de ciclo de vida de la cotización (Christian, spec 08, sección 3.3)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.quote_dto import CancelledQuoteDTO, PayAdvanceResultDTO
from app.application.ports.input.quote_lifecycle_port import ICancelQuotePort, IPayAdvancePort
from app.domain.exceptions.quote_exceptions import (
    AvailabilityConflictError,
    InvalidQuoteStateError,
    PaymentUnderReviewError,
    QuoteExpiredError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError, quote_error_to_problem
from app.infrastructure.di import containers

router = APIRouter(prefix="/quotes", tags=["Cotizaciones"])
Allowed = Annotated[AuthContext, Depends(require_role(Role.ENCARGADO, Role.SUPERADMIN))]


class CancelQuoteRequest(BaseModel):
    """Motivo opcional de la cancelación; queda solo en memoria (auditoría pendiente)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str | None = Field(default=None, max_length=500)


@router.post("/{quote_id}/pay-advance", response_model=PayAdvanceResultDTO)
async def pay_advance(
    quote_id: UUID,
    context: Allowed,
    use_case: Annotated[IPayAdvancePort, Depends(containers.get_pay_advance_use_case)],
) -> PayAdvanceResultDTO:
    try:
        return await use_case.execute(quote_id)
    except (
        AvailabilityConflictError,
        SimultaneousThresholdExceededError,
        QuoteNotFoundError,
        QuoteExpiredError,
        InvalidQuoteStateError,
        PaymentUnderReviewError,
        ValidationError,
    ) as exc:
        raise quote_error_to_problem(exc) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc


@router.post("/{quote_id}/cancel", response_model=CancelledQuoteDTO)
async def cancel_quote(
    quote_id: UUID,
    context: Allowed,
    use_case: Annotated[ICancelQuotePort, Depends(containers.get_cancel_quote_use_case)],
    payload: CancelQuoteRequest | None = None,
) -> CancelledQuoteDTO:
    try:
        return await use_case.execute(quote_id, payload.reason if payload else None)
    except (QuoteNotFoundError, InvalidQuoteStateError, ValidationError) as exc:
        raise quote_error_to_problem(exc) from exc
