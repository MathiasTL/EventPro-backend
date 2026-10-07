"""Router HTTP de procesos de control y *overrides*.

`POST /overrides/payments/{id}/approve-simultaneous` resuelve manualmente un pago en
`REQUIRES_MANUAL_APPROVAL` (RF-20, RN-04, PC-03). La aprobación es un estado del
**pago**, no del evento; cada decisión se audita.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends

from app.application.dtos.override_dto import ApproveOverbookedInput
from app.application.use_cases.payment.approve_overbooked_payment import (
    ApproveOverbookedPaymentUseCase,
)
from app.domain.exceptions.payment_exceptions import InvalidPaymentStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.override_schemas import (
    OverbookedDecisionRequest,
    OverbookedDecisionResponse,
)
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
    return OverbookedDecisionResponse.model_validate(result)
