"""Autenticación/autorización mínima para los endpoints de E5.

Diego (E2) proveerá la versión definitiva (JWT + require_role + auditoría). Aquí
se usa un JWT firmado con ``SECRET_KEY`` y el claim ``role`` para poder probar los
endpoints de pagos sin bloquear a E2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID | None
    role: str


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token requerido")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token inválido"
        ) from exc
    role = str(payload.get("role", "")).upper()
    user_id_raw = payload.get("sub")
    try:
        user_id = UUID(user_id_raw) if user_id_raw else None
    except ValueError:
        user_id = None
    return CurrentUser(user_id=user_id, role=role)


def require_role(*roles: str) -> Any:
    """Dependencia que exige uno de los roles indicados (SUPERADMIN, ENCARGADO, ...)."""

    async def checker(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if user.role not in {r.upper() for r in roles}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="rol insuficiente")
        return user

    return checker
