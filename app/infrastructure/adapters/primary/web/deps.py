from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.problem import ProblemError

_BEARER_PREFIX = "Bearer "


@dataclass(frozen=True)
class AuthContext:
    """Usuario autenticado a partir del access token JWT."""

    user_id: UUID
    role: Role


def require_role(*allowed: Role) -> Callable[..., Awaitable[AuthContext]]:
    """Dependencia reutilizable: exige un rol del panel (Matriz RBAC §3.2).

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
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise _unauthorized()
    token = authorization[len(_BEARER_PREFIX) :].strip()
    try:
        payload = decode_access_token(token, settings.secret_key)
        user_id = UUID(str(payload["sub"]))
        role = Role(str(payload["role"]))
    except Exception as exc:
        raise _unauthorized() from exc
    return AuthContext(user_id=user_id, role=role)
