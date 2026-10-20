from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.di import containers

_BEARER_PREFIX = "Bearer "


@dataclass(frozen=True)
class AuthContext:
    """Usuario autenticado con su estado y rol vigentes en la base de datos."""

    user_id: UUID
    role: Role


def require_role(*allowed: Role) -> Callable[..., Awaitable[AuthContext]]:
    """Dependencia reutilizable: exige un rol del panel (Matriz RBAC §3.2).

    El rol proviene del estado vigente del usuario (ver :func:`get_auth_context`),
    no del claim del JWT, por lo que degradaciones y desactivaciones surten efecto
    de inmediato aunque el token siga siendo válido.

    Uso: `context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN))]`
    """
    if not allowed:
        raise ValueError("require_role requiere al menos un rol")

    async def dependency(
        context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> AuthContext:
        if context.role not in allowed:
            raise ProblemError(
                403,
                "forbidden",
                "Prohibido",
                "El rol no tiene permiso para este endpoint.",
            )
        return context

    return dependency


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Token de acceso ausente, inválido o vencido.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_auth_context(
    settings: Annotated[Settings, Depends(get_settings)],
    users: Annotated[IUserRepositoryPort, Depends(containers.get_user_repository)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    """Valida el access token y lo contrasta con la cuenta vigente.

    El JWT solo demuestra identidad y firma: el rol y el estado (`is_active`)
    se leen de la base de datos en cada petición, de modo que una degradación o
    una desactivación invalida el privilegio del token de inmediato
    (401 si la cuenta no existe o está desactivada; si no, se usa el rol actual).
    """
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise _unauthorized()
    token = authorization[len(_BEARER_PREFIX) :].strip()
    try:
        payload = decode_access_token(token, settings.secret_key)
        user_id = UUID(str(payload["sub"]))
    except Exception as exc:
        raise _unauthorized() from exc
    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return AuthContext(user_id=user_id, role=user.role)
