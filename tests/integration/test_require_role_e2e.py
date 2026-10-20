"""require_role E2E: token real + app con endpoint protegido (Matriz RBAC)."""

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport
from sqlalchemy import text as sql_text

from app.core.security import hash_password
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.primary.web.deps import AuthContext, require_role
from app.infrastructure.adapters.primary.web.problem import install_exception_handlers
from app.main import app

PASSWORD = "PasswordSeguro123!"
_HASHED_PASSWORD = hash_password(PASSWORD)


async def _seed_user(role: str) -> str:
    from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker

    email = f"rbac-{uuid.uuid4().hex[:10]}@eventpro.pe"
    phone = f"+519{uuid.uuid4().int % 10**8:08d}"
    async with get_sessionmaker()() as session:
        await session.execute(
            sql_text(
                "INSERT INTO roles (code, name) VALUES "
                "('SUPERADMIN', 'Super Administrador'), "
                "('ENCARGADO', 'Encargado'), "
                "('OPERADOR', 'Operador') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        await session.execute(
            sql_text(
                "INSERT INTO users (role_id, full_name, email, phone, hashed_password) "
                "SELECT id, 'Usuario RBAC', :email, :phone, :password "
                "FROM roles WHERE code = :role"
            ),
            {"email": email, "phone": phone, "password": _HASHED_PASSWORD, "role": role},
        )
        await session.commit()
    return email


async def _token_for(email: str) -> str:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
    assert response.status_code == 200
    return response.json()["access_token"]


def _protected_app() -> FastAPI:
    scratch = FastAPI()
    install_exception_handlers(scratch)
    secured = APIRouter()

    @secured.get("/solo-superadmin")
    async def solo_superadmin(
        context: Annotated[AuthContext, Depends(require_role(Role.SUPERADMIN))],
    ) -> dict[str, str]:
        return {"role": context.role.value}

    scratch.include_router(secured)
    return scratch


async def _get_with_token(token: str | None) -> httpx.Response:
    transport = ASGITransport(app=_protected_app())
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/solo-superadmin", headers=headers)


async def test_superadmin_passes_require_role(infra: None) -> None:
    email = await _seed_user("SUPERADMIN")
    token = await _token_for(email)

    response = await _get_with_token(token)

    assert response.status_code == 200
    assert response.json() == {"role": "SUPERADMIN"}


async def test_encargado_gets_403_forbidden(infra: None) -> None:
    email = await _seed_user("ENCARGADO")
    token = await _token_for(email)

    response = await _get_with_token(token)

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://errors.eventpro.pe/forbidden"


async def test_missing_token_gets_401(infra: None) -> None:
    response = await _get_with_token(None)

    assert response.status_code == 401
    assert response.json()["type"] == "https://errors.eventpro.pe/invalid-credentials"
