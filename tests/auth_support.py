"""Dobles de autenticación para tests unitarios de la API.

`get_auth_context` valida la cuenta contra el repositorio de usuarios en cada
petición (auth fresca), así que los tests unitarios instalan
`StubUserRepository` con `install(app)` y fijan el rol vigente del actor con
`set_role(role)` — el helper de token de cada archivo lo hace junto al claim.
"""

from uuid import UUID

from fastapi import FastAPI

from app.domain.entities.user import User
from app.domain.value_objects.role import Role
from app.infrastructure.di import containers

PHONE = "+519000000000"


class _CurrentAuth:
    def __init__(self) -> None:
        self.role: Role = Role.SUPERADMIN
        self.is_active: bool = True


CURRENT = _CurrentAuth()


def set_role(role: Role) -> None:
    """Fija el rol que StubUserRepository devolverá (el rol vigente en BD)."""
    CURRENT.role = role


class StubUserRepository:
    """Repositorio mínimo para get_auth_context: una cuenta con el rol vigente."""

    async def get_by_id(self, user_id: UUID) -> User:
        return User(
            id=user_id,
            full_name="Usuario de prueba",
            email=f"{user_id.hex[:12]}@eventpro.pe",
            phone=PHONE,
            role=CURRENT.role,
            hashed_password="x",
            is_active=CURRENT.is_active,
        )

    async def get_by_email(self, email: str) -> None:
        return None

    async def add(self, user: User) -> None:
        raise NotImplementedError("StubUserRepository no crea usuarios")

    async def update(self, user_id: UUID, patch: object) -> User:
        raise NotImplementedError("StubUserRepository no actualiza usuarios")

    async def list(self, filters: object) -> tuple[User, ...]:
        return ()

    async def count(self, filters: object) -> int:
        return 0


def install(app: FastAPI) -> None:
    """Fija el repositorio de usuarios stub para que get_auth_context pase."""
    app.dependency_overrides[containers.get_user_repository] = lambda: StubUserRepository()
