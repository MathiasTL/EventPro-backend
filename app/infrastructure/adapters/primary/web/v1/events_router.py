"""Adaptador primario de cronograma e inicio: traduce HTTP a puertos de aplicación."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request

from app.application.dtos.event_schedule_dto import EventScheduleFilters, ScheduleActor
from app.application.ports.input.event_schedule_port import IGetEventSchedulePort
from app.application.ports.input.event_start_port import IStartEventPort
from app.application.use_cases.event.get_event_schedule import ScheduleAssignmentRequiredError
from app.application.use_cases.event.start_event import EventAccessDeniedError
from app.domain.exceptions.event_exceptions import BalancePendingError, InvalidEventStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.infrastructure.adapters.primary.web.deps import AuthContext, get_auth_context
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.event_schemas import (
    EventScheduleResponse,
    StartEventRequest,
    StartEventResponse,
)
from app.infrastructure.di.containers import get_event_schedule_use_case, get_start_event_use_case

router = APIRouter(prefix="/events", tags=["Eventos"])
_EMPTY_START_REQUEST = StartEventRequest()


@router.get(
    "/schedule",
    response_model=list[EventScheduleResponse],
    summary="Consultar el cronograma de eventos",
    description=(
        "Slice 1: filtros inclusivos por fechas y estado. Los datos de cliente, paquete, "
        "temática y elenco provienen de fakes temporales. OPERADOR requiere una asignación. "
        "district, theme_id y crew_id se incorporarán en una entrega posterior."
    ),
    responses={
        401: {"description": "Autenticación requerida"},
        403: {"description": "El operador requiere asignación activa"},
    },
)
async def get_schedule(
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    use_case: Annotated[IGetEventSchedulePort, Depends(get_event_schedule_use_case)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    status: Annotated[EventStatus | None, Query()] = None,
) -> list[EventScheduleResponse]:
    deferred = {"district", "theme_id", "crew_id"}.intersection(request.query_params)
    if deferred:
        raise ProblemError(
            422,
            "validation-error",
            "Error de validación",
            f"Filtros aún no disponibles en Slice 1: {', '.join(sorted(deferred))}.",
        )
    try:
        result = await use_case.execute(
            EventScheduleFilters(from_date=from_date, to_date=to_date, status=status),
            ScheduleActor(user_id=context.user_id, role=context.role),
        )
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    except ScheduleAssignmentRequiredError as exc:
        raise ProblemError(403, "forbidden", "Prohibido", str(exc)) from exc
    return [EventScheduleResponse.model_validate(item) for item in result]


@router.post(
    "/{event_id}/start",
    response_model=StartEventResponse,
    summary="Iniciar el evento con saldo pre-show verificado",
    description=(
        "US-17 parcial: SCHEDULED o AWAITING_BALANCE → IN_PROGRESS, con saldo verificado "
        "mediante un Fake temporal de E5. El servidor registra la hora UTC. No registra "
        "pagos nuevos ni recibe importes, evidencia o fechas del cliente."
    ),
    responses={
        400: {"description": "Saldo verificado insuficiente"},
        401: {"description": "Autenticación requerida"},
        403: {"description": "El operador no tiene asignación al evento"},
        404: {"description": "Evento no encontrado"},
        409: {"description": "Estado incompatible o inicio previo"},
    },
)
async def start_event(
    event_id: UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    use_case: Annotated[IStartEventPort, Depends(get_start_event_use_case)],
    payload: Annotated[StartEventRequest, Body()] = _EMPTY_START_REQUEST,
) -> StartEventResponse:
    try:
        result = await use_case.execute(
            event_id, ScheduleActor(user_id=context.user_id, role=context.role)
        )
    except EventAccessDeniedError as exc:
        raise ProblemError(403, "forbidden", "Prohibido", str(exc)) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    except InvalidEventStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    except BalancePendingError as exc:
        raise ProblemError(400, exc.code, "Saldo pendiente", str(exc)) from exc
    return StartEventResponse.model_validate(result)
