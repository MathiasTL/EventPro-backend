"""Router HTTP de procesos de control y *overrides*.

`POST /overrides/payments/{id}/approve-simultaneous` resuelve manualmente un pago en
`REQUIRES_MANUAL_APPROVAL` (RF-20, RN-04, PC-03). La aprobación es un estado del
**pago**, no del evento; cada decisión se audita.

`PATCH /overrides/quotes/{id}/mobility` sobrescribe el monto de movilidad de una
cotización (RF-21, PC-04) y `PATCH /overrides/crew-assignments/{id}/transit-interval`
ajusta el intervalo mínimo de tránsito de una asignación de elenco (RF-22, PC-02).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.override_dto import (
    ApproveOverbookedInput,
    OverrideMobilityInput,
    OverrideTransitIntervalInput,
)
from app.application.use_cases.crew.override_transit_interval import (
    OverrideCrewTransitIntervalUseCase,
)
from app.application.use_cases.payment.approve_overbooked_payment import (
    ApproveOverbookedPaymentUseCase,
)
from app.application.use_cases.quote.override_mobility import OverrideQuoteMobilityUseCase
from app.domain.exceptions.event_exceptions import InvalidEventStateError
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.override_schemas import (
    MobilityOverrideRequest,
    MobilityOverrideResponse,
    OverbookedDecisionRequest,
    OverbookedDecisionResponse,
    TransitIntervalOverrideRequest,
    TransitIntervalOverrideResponse,
)
from app.infrastructure.adapters.secondary.persistence.database import get_contract_write_session
from app.infrastructure.di import containers

router = APIRouter(prefix="/overrides", tags=["Procesos de control"])

_STAFF = (Role.ENCARGADO, Role.SUPERADMIN)


@router.post(
    "/payments/{payment_id}/approve-simultaneous",
    response_model=OverbookedDecisionResponse,
)
async def decide_overbooked_payment(
    payment_id: UUID,
    payload: Annotated[OverbookedDecisionRequest, Body()],
    transaction: Annotated[AsyncSession, Depends(get_contract_write_session, scope="function")],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[
        ApproveOverbookedPaymentUseCase,
        Depends(containers.get_approve_overbooked_payment_use_case),
    ],
) -> OverbookedDecisionResponse:
    try:
        result = await use_case.execute(
            ApproveOverbookedInput(
                payment_id=payment_id,
                decision=payload.action,
                decided_by_user_id=context.user_id,
                notes=payload.notes,
                event_id=payload.event_id,
            )
        )
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "resource-not-found", "No encontrado", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    except InvalidPaymentStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    except ResourceInUseError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    return OverbookedDecisionResponse.model_validate(result)


@router.patch("/quotes/{quote_id}/mobility", response_model=MobilityOverrideResponse)
async def override_quote_mobility(
    quote_id: UUID,
    payload: Annotated[MobilityOverrideRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[
        OverrideQuoteMobilityUseCase,
        Depends(containers.get_override_quote_mobility_use_case),
    ],
) -> MobilityOverrideResponse:
    try:
        result = await use_case.execute(
            OverrideMobilityInput(
                quote_id=quote_id,
                manual_mobility_amount=payload.manual_mobility_amount,
                reason=payload.reason,
                decided_by_user_id=context.user_id,
            )
        )
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "resource-not-found", "No encontrado", str(exc)) from exc
    except InvalidQuoteStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    return MobilityOverrideResponse.model_validate(result)


@router.patch(
    "/crew-assignments/{assignment_id}/transit-interval",
    response_model=TransitIntervalOverrideResponse,
)
async def override_crew_transit_interval(
    assignment_id: UUID,
    payload: Annotated[TransitIntervalOverrideRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[
        OverrideCrewTransitIntervalUseCase,
        Depends(containers.get_override_crew_transit_interval_use_case),
    ],
) -> TransitIntervalOverrideResponse:
    try:
        result = await use_case.execute(
            OverrideTransitIntervalInput(
                assignment_id=assignment_id,
                transit_interval_minutes=payload.transit_interval_minutes,
                reason=payload.reason,
                decided_by_user_id=context.user_id,
            )
        )
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "resource-not-found", "No encontrado", str(exc)) from exc
    except InvalidEventStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    return TransitIntervalOverrideResponse.model_validate(result)
