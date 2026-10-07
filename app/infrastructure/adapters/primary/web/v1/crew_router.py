"""Router HTTP del módulo de elencos (RF-29, US-26).

Gestión de los elencos freelance y de su vínculo con usuarios ``OPERADOR``. Solo los
roles ``ENCARGADO`` y ``SUPERADMIN`` administran elencos.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends

from app.application.use_cases.crew.manage_crews import ManageCrewsUseCase
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.crew_schemas import (
    CrewListResponse,
    CrewPatchRequest,
    CrewRequest,
    CrewResponse,
)
from app.infrastructure.di import containers

router = APIRouter(prefix="/crews", tags=["Elencos"])

_STAFF = (Role.ENCARGADO, Role.SUPERADMIN)


@router.get("", response_model=CrewListResponse)
async def list_crews(
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCrewsUseCase, Depends(containers.get_manage_crews_use_case)],
) -> CrewListResponse:
    crews = await use_case.list_crews()
    items = [CrewResponse.model_validate(crew) for crew in crews]
    return CrewListResponse(items=items, total=len(items))


@router.post("", response_model=CrewResponse, status_code=201)
async def create_crew(
    payload: Annotated[CrewRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCrewsUseCase, Depends(containers.get_manage_crews_use_case)],
) -> CrewResponse:
    try:
        result = await use_case.create_crew(
            leader_name=payload.leader_name,
            phone=payload.phone,
            service_category=payload.service_category,
            user_id=payload.user_id,
        )
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "resource-not-found", "No encontrado", str(exc)) from exc
    except DuplicateResourceError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    return CrewResponse.model_validate(result)


@router.patch("/{crew_id}", response_model=CrewResponse)
async def update_crew(
    crew_id: UUID,
    payload: Annotated[CrewPatchRequest, Body()],
    context: Annotated[AuthContext, Depends(require_role(*_STAFF))],
    use_case: Annotated[ManageCrewsUseCase, Depends(containers.get_manage_crews_use_case)],
) -> CrewResponse:
    try:
        result = await use_case.update_crew(
            crew_id,
            leader_name=payload.leader_name,
            phone=payload.phone,
            service_category=payload.service_category,
            user_id=payload.user_id,
            user_id_provided="user_id" in payload.model_fields_set,
            is_active=payload.is_active,
        )
    except ValidationError as exc:
        raise ProblemError(422, "validation-error", "Error de validación", str(exc)) from exc
    except ResourceNotFoundError as exc:
        raise ProblemError(404, "resource-not-found", "No encontrado", str(exc)) from exc
    except DuplicateResourceError as exc:
        raise ProblemError(409, exc.code, "Conflicto", str(exc)) from exc
    return CrewResponse.model_validate(result)
