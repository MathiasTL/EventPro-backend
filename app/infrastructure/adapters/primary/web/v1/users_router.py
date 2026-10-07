"""Router HTTP del módulo de usuarios del panel (US-23, RBAC solo SUPERADMIN)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.application.dtos.user_dto import CreateUserInput, UpdateUserInput, UserFilters
from app.application.use_cases.users.create_user import CreateUserUseCase
from app.application.use_cases.users.errors import SelfModificationError
from app.application.use_cases.users.get_user import GetUserUseCase
from app.application.use_cases.users.list_users import ListUsersUseCase
from app.application.use_cases.users.update_user import UpdateUserUseCase
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.schemas.user_schemas import (
    UserCreateRequest,
    UserPageResponse,
    UserReadResponse,
    UserUpdateRequest,
)
from app.infrastructure.di import containers

router = APIRouter(prefix="/users", tags=["Usuarios"])


def _duplicate(exc: DuplicateResourceError) -> ProblemError:
    return ProblemError(409, exc.code, "Conflicto", str(exc))


def _not_found(exc: ResourceNotFoundError) -> ProblemError:
    return ProblemError(404, exc.code, "No encontrado", str(exc))


@router.get("", response_model=UserPageResponse)
async def list_users(
    context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN))],
    use_case: Annotated[ListUsersUseCase, Depends(containers.get_list_users_use_case)],
    role: Annotated[Role | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserPageResponse:
    """Lista paginada de usuarios; filtros `role`, `is_active` y `q` (nombre/correo/teléfono)."""
    result = await use_case.execute(
        UserFilters(role=role, is_active=is_active, q=q, page=page, page_size=page_size)
    )
    return UserPageResponse(
        items=[UserReadResponse.model_validate(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post("", response_model=UserReadResponse, status_code=201)
async def create_user(
    payload: UserCreateRequest,
    context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN))],
    use_case: Annotated[CreateUserUseCase, Depends(containers.get_create_user_use_case)],
) -> UserReadResponse:
    """Crea un usuario con su rol; la contraseña se guarda con hash y nunca se devuelve."""
    try:
        result = await use_case.execute(
            CreateUserInput(
                full_name=payload.full_name,
                email=payload.email,
                phone=payload.phone,
                role=payload.role,
                password=payload.password,
            )
        )
    except DuplicateResourceError as exc:
        raise _duplicate(exc) from exc
    return UserReadResponse.model_validate(result)


@router.get("/{user_id}", response_model=UserReadResponse)
async def get_user(
    user_id: UUID,
    context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN))],
    use_case: Annotated[GetUserUseCase, Depends(containers.get_get_user_use_case)],
) -> UserReadResponse:
    try:
        result = await use_case.execute(user_id)
    except ResourceNotFoundError as exc:
        raise _not_found(exc) from exc
    return UserReadResponse.model_validate(result)


@router.patch("/{user_id}", response_model=UserReadResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN))],
    use_case: Annotated[UpdateUserUseCase, Depends(containers.get_update_user_use_case)],
) -> UserReadResponse:
    """Actualiza datos/rol/estado/contraseña; desactivar o cambiar la clave revoca sus tokens."""
    try:
        result = await use_case.execute(
            context.user_id,
            user_id,
            UpdateUserInput(
                full_name=payload.full_name,
                phone=payload.phone,
                role=payload.role,
                is_active=payload.is_active,
                password=payload.password,
            ),
        )
    except SelfModificationError as exc:
        raise ProblemError(403, exc.code, "Prohibido", str(exc)) from exc
    except ResourceNotFoundError as exc:
        raise _not_found(exc) from exc
    except DuplicateResourceError as exc:
        raise _duplicate(exc) from exc
    except ValidationError as exc:
        raise ProblemError(422, exc.code, "Error de validación", str(exc)) from exc
    return UserReadResponse.model_validate(result)
