"""Adaptador primario de US-16: traducción HTTP y delegación al puerto de entrada."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.application.dtos.event_schedule_dto import EventScheduleFilters, ScheduleActor
from app.application.ports.input.event_schedule_port import IGetEventSchedulePort
from app.application.use_cases.event.get_event_schedule import ScheduleAssignmentRequiredError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.event_status import EventStatus
from app.infrastructure.adapters.primary.web.deps import AuthContext, get_auth_context
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.event_schemas import EventScheduleResponse
from app.infrastructure.di.containers import get_event_schedule_use_case

router = APIRouter(prefix="/events", tags=["Eventos"])


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
