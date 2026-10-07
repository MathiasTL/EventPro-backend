"""Adaptador primario de cronograma e inicio: traduce HTTP a puertos de aplicación."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Form, Query, Request

from app.application.dtos.event_extension_dto import RegisterEventExtensionInput
from app.application.dtos.event_schedule_dto import EventScheduleFilters, ScheduleActor
from app.application.ports.input.event_extension_port import (
    IRegisterEventExtensionPort,
    ISettleEventPort,
)
from app.application.ports.input.event_schedule_port import IGetEventSchedulePort
from app.application.ports.input.event_start_port import IStartEventPort
from app.application.use_cases.event.access_errors import EventRoleForbiddenError
from app.application.use_cases.event.get_event_schedule import ScheduleAssignmentRequiredError
from app.application.use_cases.event.start_event import EventAccessDeniedError
from app.domain.exceptions.event_exceptions import (
    BalancePendingError,
    EventResourceConflictError,
    ExtensionPaymentMismatchError,
    InvalidEventStateError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.exceptions.storage_exceptions import EvidenceValidationError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, get_auth_context, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.event_schemas import (
    EventExtensionRequest,
    EventExtensionResponse,
    EventScheduleResponse,
    SettleEventRequest,
    SettleEventResponse,
    StartEventRequest,
    StartEventResponse,
)
from app.infrastructure.di.containers import (
    get_event_schedule_use_case,
    get_register_event_extension_use_case,
    get_settle_event_use_case,
    get_start_event_use_case,
)

router = APIRouter(prefix="/events", tags=["Eventos"])
_EMPTY_START_REQUEST = StartEventRequest()
_EMPTY_SETTLE_REQUEST = SettleEventRequest()


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
    except (EventAccessDeniedError, EventRoleForbiddenError) as exc:
        raise ProblemError(403, "forbidden", "Prohibido", str(exc)) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    except InvalidEventStateError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    except BalancePendingError as exc:
        raise ProblemError(400, exc.code, "Saldo pendiente", str(exc)) from exc
    return StartEventResponse.model_validate(result)


@router.post(
    "/{event_id}/extensions",
    response_model=EventExtensionResponse,
    status_code=201,
    summary="Registrar una extensión cobrada con evidencia",
    description=(
        "IN_PROGRESS o EXTENDED → EXTENDED. agreed_rate es el importe total pactado. "
        "Cada registro crea una extensión y un pago EXTENSION VERIFIED, "
        "pendiente de auditoría."
    ),
    responses={
        401: {"description": "Autenticación requerida"},
        403: {"description": "Rol no permitido"},
        404: {"description": "Evento inexistente o fuera de alcance"},
        409: {"description": "Estado incompatible o conflicto de recursos/traslado/sobrecupo"},
        422: {"description": "Datos o evidencia inválidos"},
    },
)
async def register_event_extension(
    event_id: UUID,
    context: Annotated[
        AuthContext, Depends(require_role(Role.OPERADOR, Role.ENCARGADO, Role.SUPERADMIN))
    ],
    use_case: Annotated[
        IRegisterEventExtensionPort, Depends(get_register_event_extension_use_case)
    ],
    payload: Annotated[EventExtensionRequest, Form(media_type="multipart/form-data")],
) -> EventExtensionResponse:
    try:
        data = await payload.evidence_file.read(5 * 1024 * 1024 + 1)
        result = await use_case.execute(
            RegisterEventExtensionInput(
                event_id,
                payload.extra_minutes,
                payload.agreed_rate,
                payload.payment_method,
                data,
                payload.evidence_file.content_type or "",
                payload.evidence_file.filename or "evidence",
                payload.transaction_reference,
            ),
            ScheduleActor(context.user_id, context.role),
        )
    except EventRoleForbiddenError as exc:
        raise ProblemError(403, "forbidden", "Prohibido", str(exc)) from exc
    except EvidenceValidationError as exc:
        raise ProblemError(422, exc.code, "Comprobante inválido", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    except (
        InvalidEventStateError,
        ExtensionPaymentMismatchError,
        EventResourceConflictError,
    ) as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    return EventExtensionResponse.model_validate(result)


@router.post(
    "/{event_id}/settle",
    response_model=SettleEventResponse,
    summary="Liquidar un evento con todos sus cobros cubiertos",
    description=(
        "IN_PROGRESS o EXTENDED → SETTLED. Usa los cobros base guardados en Event "
        "y comprueba las extensiones contra los pagos reales de E5."
    ),
    responses={
        400: {"description": "Saldo pendiente"},
        401: {"description": "Autenticación requerida"},
        403: {"description": "Rol no permitido"},
        404: {"description": "Evento inexistente o fuera de alcance"},
        409: {"description": "Estado incompatible o extensiones inconsistentes"},
    },
)
async def settle_event(
    event_id: UUID,
    context: Annotated[
        AuthContext, Depends(require_role(Role.OPERADOR, Role.ENCARGADO, Role.SUPERADMIN))
    ],
    use_case: Annotated[ISettleEventPort, Depends(get_settle_event_use_case)],
    payload: Annotated[SettleEventRequest, Body()] = _EMPTY_SETTLE_REQUEST,
) -> SettleEventResponse:
    try:
        result = await use_case.execute(event_id, ScheduleActor(context.user_id, context.role))
    except EventRoleForbiddenError as exc:
        raise ProblemError(403, "forbidden", "Prohibido", str(exc)) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "not-found", "No encontrado", str(exc)) from exc
    except (InvalidEventStateError, ExtensionPaymentMismatchError) as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    except BalancePendingError as exc:
        raise ProblemError(400, exc.code, "Saldo pendiente", str(exc)) from exc
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    return SettleEventResponse.model_validate(result)
