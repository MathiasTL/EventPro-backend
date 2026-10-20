from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.application.use_cases.auth.dto import AuthSession
from app.application.use_cases.auth.errors import InvalidCredentialsError, UserInactiveError
from app.application.use_cases.auth.login import LoginUseCase
from app.application.use_cases.auth.logout import LogoutUseCase
from app.application.use_cases.auth.refresh import RefreshUseCase
from app.infrastructure.adapters.primary.web.deps import AuthContext, get_auth_context
from app.infrastructure.adapters.primary.web.problem import ProblemError
from app.infrastructure.adapters.primary.web.rate_limit import limiter
from app.infrastructure.di.containers import (
    get_login_use_case,
    get_logout_use_case,
    get_refresh_use_case,
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])

_LOGIN_REQUIRED_ERROR = "Correo o contraseña incorrectos."
_REFRESH_REQUIRED_ERROR = "Refresh token inválido, revocado o vencido."


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=64)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=64)


def _invalid_credentials() -> ProblemError:
    return ProblemError(
        401,
        "invalid-credentials",
        "No autorizado",
        _LOGIN_REQUIRED_ERROR,
    )


def _user_inactive() -> ProblemError:
    return ProblemError(403, "user-inactive", "Prohibido", "La cuenta está desactivada.")


def _tokens_content(session: AuthSession) -> dict[str, object]:
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_in": session.expires_in,
    }


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    use_case: Annotated[LoginUseCase, Depends(get_login_use_case)],
) -> JSONResponse:
    try:
        session = await use_case.execute(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise _invalid_credentials() from exc
    except UserInactiveError as exc:
        raise _user_inactive() from exc
    content = _tokens_content(session)
    content["token_type"] = "bearer"
    if session.user is not None:
        content["user"] = {
            "id": str(session.user.id),
            "full_name": session.user.full_name,
            "role": session.user.role.value,
        }
    return JSONResponse(status_code=200, content=content)


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    use_case: Annotated[RefreshUseCase, Depends(get_refresh_use_case)],
) -> JSONResponse:
    try:
        session = await use_case.execute(body.refresh_token)
    except InvalidCredentialsError as exc:
        raise ProblemError(
            401,
            "invalid-credentials",
            "No autorizado",
            _REFRESH_REQUIRED_ERROR,
        ) from exc
    except UserInactiveError as exc:
        raise _user_inactive() from exc
    return JSONResponse(status_code=200, content=_tokens_content(session))


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutRequest,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    use_case: Annotated[LogoutUseCase, Depends(get_logout_use_case)],
) -> Response:
    await use_case.execute(context.user_id, body.refresh_token)
    return Response(status_code=204)
