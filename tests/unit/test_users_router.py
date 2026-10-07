from collections.abc import Iterator, Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.dtos.user_dto import UserFilters, UserPatch
from app.application.use_cases.users.create_user import CreateUserUseCase
from app.application.use_cases.users.get_user import GetUserUseCase
from app.application.use_cases.users.list_users import ListUsersUseCase
from app.application.use_cases.users.update_user import UpdateUserUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.entities.user import User
from app.domain.exceptions.resource_exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.role import Role
from app.infrastructure.di import containers
from app.main import create_app
from tests.auth_support import CURRENT, set_role

PATH = "/api/v1/users"
ACTOR_ID = uuid4()
PASSWORD = "PasswordTemporal123!"
DUPLICATE_MESSAGE = "El correo o el teléfono ya están registrados."
LAST_SUPERADMIN_MESSAGE = "El sistema debe conservar al menos un SUPERADMIN activo."


class FakeTokenRepository:
    """Revocación de refresh tokens observada por los tests (US-23)."""

    def __init__(self) -> None:
        self.revoked: set[UUID] = set()

    async def revoke_for(self, user_id: UUID) -> None:
        self.revoked.add(user_id)


class FakeUserRepository:
    """Repositorio de usuarios con la semántica de la implementación SQL.

    `update` replica el contrato del puerto: parche atómico, invariantes,
    revocación de refresh tokens previa a la escritura y errores de dominio.
    El actor de prueba (ACTOR_ID) no existe en la base del test: si no está
    sembrado, `get_by_id` devuelve una cuenta sintética con el rol vigente
    fijado por `set_role` (auth fresca).
    """

    def __init__(self, tokens: FakeTokenRepository | None = None) -> None:
        self._items: dict[UUID, User] = {}
        self.tokens = tokens if tokens is not None else FakeTokenRepository()

    def seed(self, user: User) -> User:
        self._items[user.id] = user
        return user

    async def get_by_email(self, email: str) -> User | None:
        target = email.strip().lower()
        for user in self._items.values():
            if user.email.lower() == target:
                return user
        return None

    async def get_by_id(self, user_id: UUID) -> User | None:
        existing = self._items.get(user_id)
        if existing is not None:
            return existing
        if user_id == ACTOR_ID:
            return User(
                id=ACTOR_ID,
                full_name="Super Admin",
                email="super@eventpro.pe",
                phone="+519000000001",
                role=CURRENT.role,
                hashed_password="x",
            )
        return None

    async def add(self, user: User) -> None:
        if await self.get_by_email(user.email) is not None:
            raise DuplicateResourceError(DUPLICATE_MESSAGE)
        if any(item.phone == user.phone for item in self._items.values()):
            raise DuplicateResourceError(DUPLICATE_MESSAGE)
        self._items[user.id] = user

    async def update(self, user_id: UUID, patch: UserPatch) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario no existe.")
        candidate = replace(
            user,
            full_name=patch.full_name if patch.full_name is not None else user.full_name,
            phone=patch.phone if patch.phone is not None else user.phone,
            role=patch.role if patch.role is not None else user.role,
            is_active=patch.is_active if patch.is_active is not None else user.is_active,
            hashed_password=(
                patch.password_hash if patch.password_hash is not None else user.hashed_password
            ),
        )
        if any(
            item.phone == candidate.phone and item.id != user_id for item in self._items.values()
        ):
            raise DuplicateResourceError(DUPLICATE_MESSAGE)
        was_active_superadmin = user.is_active and user.role is Role.SUPERADMIN
        still_active_superadmin = candidate.is_active and candidate.role is Role.SUPERADMIN
        if (
            was_active_superadmin
            and not still_active_superadmin
            and not any(
                item.is_active and item.role is Role.SUPERADMIN and item.id != user_id
                for item in self._items.values()
            )
        ):
            raise ValidationError(LAST_SUPERADMIN_MESSAGE)
        if patch.revoke_refresh_tokens:
            await self.tokens.revoke_for(user_id)
        self._items[user_id] = candidate
        return candidate

    async def list(self, filters: UserFilters) -> Sequence[User]:
        matches = self._matching(filters)
        start = (max(1, filters.page) - 1) * max(1, filters.page_size)
        return tuple(matches[start : start + filters.page_size])

    async def count(self, filters: UserFilters) -> int:
        return len(self._matching(filters))

    def _matching(self, filters: UserFilters) -> "list[User]":
        matches = list(self._items.values())
        if filters.role is not None:
            matches = [item for item in matches if item.role is filters.role]
        if filters.is_active is not None:
            matches = [item for item in matches if item.is_active is filters.is_active]
        if filters.q and filters.q.strip():
            term = filters.q.strip().lower()
            matches = [
                item
                for item in matches
                if term in item.full_name.lower()
                or term in item.email.lower()
                or term in item.phone.lower()
            ]
        matches.sort(key=lambda item: item.full_name.lower())
        return matches


def authorization(role: Role = Role.SUPERADMIN, user_id: UUID = ACTOR_ID) -> dict[str, str]:
    set_role(role)
    token = create_access_token(
        subject=str(user_id), role=role.value, secret_key=get_settings().secret_key
    )
    return {"Authorization": f"Bearer {token}"}


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "full_name": "María Gómez",
        "email": "operador1@eventpro.pe",
        "phone": "+519111222333",
        "role": "OPERADOR",
        "password": PASSWORD,
    }
    body.update(overrides)
    return body


@pytest.fixture
def web_app() -> Iterator[FastAPI]:
    app = create_app()
    tokens = FakeTokenRepository()
    users = FakeUserRepository(tokens)
    app.state.users = users
    app.state.tokens = tokens
    app.dependency_overrides[containers.get_user_repository] = lambda: users
    app.dependency_overrides[containers.get_list_users_use_case] = lambda: ListUsersUseCase(users)
    app.dependency_overrides[containers.get_create_user_use_case] = lambda: CreateUserUseCase(users)
    app.dependency_overrides[containers.get_get_user_use_case] = lambda: GetUserUseCase(users)
    app.dependency_overrides[containers.get_update_user_use_case] = lambda: UpdateUserUseCase(users)
    yield app
    app.dependency_overrides.clear()


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer invalid"}])
async def test_users_require_authentication(
    web_app: FastAPI, headers: dict[str, str] | None
) -> None:
    async with _client(web_app) as client:
        response = await client.get(PATH, headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.OPERADOR])
async def test_non_superadmin_cannot_manage_users(web_app: FastAPI, role: Role) -> None:
    async with _client(web_app) as client:
        listed = await client.get(PATH, headers=authorization(role))
        created = await client.post(PATH, headers=authorization(role), json=payload())
        patched = await client.patch(
            f"{PATH}/{uuid4()}", headers=authorization(role), json={"is_active": False}
        )
    assert listed.status_code == 403
    assert created.status_code == 403
    assert patched.status_code == 403


async def test_create_user_returns_201_without_password(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        response = await client.post(PATH, headers=authorization(), json=payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "OPERADOR"
    assert body["is_active"] is True
    assert body["email"] == "operador1@eventpro.pe"
    assert "password" not in body
    assert "hashed_password" not in body


async def test_create_duplicate_email_returns_409(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        first = await client.post(PATH, headers=authorization(), json=payload())
        second = await client.post(
            PATH,
            headers=authorization(),
            json=payload(email="OPERADOR1@EventPro.pe", phone="+519111222344"),
        )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["type"].endswith("duplicate-resource")


async def test_create_duplicate_phone_returns_409(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        first = await client.post(PATH, headers=authorization(), json=payload())
        second = await client.post(
            PATH,
            headers=authorization(),
            json=payload(email="otro@eventpro.pe", phone=first.json()["phone"]),
        )
    assert first.status_code == 201
    assert second.status_code == 409


async def test_create_invalid_payload_returns_422(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        short = await client.post(PATH, headers=authorization(), json=payload(password="corta"))
        bad_role = await client.post(PATH, headers=authorization(), json=payload(role="NADIE"))
        bad_email = await client.post(
            PATH, headers=authorization(), json=payload(email="sin-arroba")
        )
    assert short.status_code == 422
    assert bad_role.status_code == 422
    assert bad_email.status_code == 422


async def test_phone_exceeding_column_length_returns_422(web_app: FastAPI) -> None:
    long_phone = "+519" + "1" * 17
    assert len(long_phone) == 21
    async with _client(web_app) as client:
        created = await client.post(PATH, headers=authorization(), json=payload())
        on_create = await client.post(PATH, headers=authorization(), json=payload(phone=long_phone))
        on_patch = await client.patch(
            f"{PATH}/{created.json()['id']}",
            headers=authorization(),
            json={"phone": long_phone},
        )
    assert on_create.status_code == 422
    assert on_patch.status_code == 422


async def test_create_maps_domain_validation_error_to_422(web_app: FastAPI) -> None:
    class _MissingRoleSeed:
        async def execute(self, data: object) -> object:
            raise ValidationError("El rol OPERADOR no existe; ejecute el seed de roles.")

    web_app.dependency_overrides[containers.get_create_user_use_case] = lambda: _MissingRoleSeed()
    async with _client(web_app) as client:
        response = await client.post(PATH, headers=authorization(), json=payload())
    assert response.status_code == 422
    assert response.json()["type"].endswith("validation-error")


async def test_list_users_paginates_and_filters(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        for index in range(3):
            created = await client.post(
                PATH,
                headers=authorization(),
                json=payload(
                    full_name=f"Operador {index}",
                    email=f"operador{index}@eventpro.pe",
                    phone=f"+51911122233{index}",
                    role="OPERADOR" if index < 2 else "ENCARGADO",
                ),
            )
            assert created.status_code == 201, created.text
        page = await client.get(PATH, headers=authorization(), params={"page_size": 2})
        operators = await client.get(PATH, headers=authorization(), params={"role": "OPERADOR"})
        inactive = await client.get(PATH, headers=authorization(), params={"is_active": "false"})
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    assert operators.json()["total"] == 2
    assert inactive.json()["total"] == 0


async def test_list_users_searches_by_q(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        await client.post(PATH, headers=authorization(), json=payload())
        await client.post(
            PATH,
            headers=authorization(),
            json=payload(
                full_name="Juan Pérez",
                email="juan@eventpro.pe",
                phone="+519888777666",
            ),
        )
        by_name = await client.get(PATH, headers=authorization(), params={"q": "juan"})
        by_email = await client.get(PATH, headers=authorization(), params={"q": "@eventpro.pe"})
        by_phone = await client.get(PATH, headers=authorization(), params={"q": "9888777"})
        empty = await client.get(PATH, headers=authorization(), params={"q": "no-existe"})
    assert by_name.json()["total"] == 1
    assert by_name.json()["items"][0]["full_name"] == "Juan Pérez"
    assert by_email.json()["total"] == 2
    assert by_phone.json()["total"] == 1
    assert empty.json()["total"] == 0


async def test_get_user_returns_200_and_404(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        created = await client.post(PATH, headers=authorization(), json=payload())
        user_id = created.json()["id"]
        found = await client.get(f"{PATH}/{user_id}", headers=authorization())
        missing = await client.get(f"{PATH}/{uuid4()}", headers=authorization())
    assert found.status_code == 200
    assert found.json()["id"] == user_id
    assert missing.status_code == 404


async def test_patch_updates_fields(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        created = await client.post(PATH, headers=authorization(), json=payload())
        user_id = created.json()["id"]
        patched = await client.patch(
            f"{PATH}/{user_id}",
            headers=authorization(),
            json={
                "full_name": "María Gómez Salas",
                "phone": "+519111222444",
                "role": "ENCARGADO",
            },
        )
        detail = await client.get(f"{PATH}/{user_id}", headers=authorization())
    assert patched.status_code == 200, patched.text
    assert patched.json()["full_name"] == "María Gómez Salas"
    assert patched.json()["role"] == "ENCARGADO"
    assert detail.json()["phone"] == "+519111222444"


async def test_patch_deactivate_revokes_refresh_tokens(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        created = await client.post(PATH, headers=authorization(), json=payload())
        user_id = created.json()["id"]
        patched = await client.patch(
            f"{PATH}/{user_id}", headers=authorization(), json={"is_active": False}
        )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False
    assert user_id in {str(item) for item in web_app.state.tokens.revoked}


async def test_patch_password_change_revokes_refresh_tokens(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        created = await client.post(PATH, headers=authorization(), json=payload())
        user_id = created.json()["id"]
        patched = await client.patch(
            f"{PATH}/{user_id}", headers=authorization(), json={"password": "NuevaClave456!"}
        )
    assert patched.status_code == 200
    assert "password" not in patched.json()
    assert user_id in {str(item) for item in web_app.state.tokens.revoked}


async def test_patch_cannot_deactivate_self(web_app: FastAPI) -> None:
    web_app.state.users.seed(
        User(
            id=ACTOR_ID,
            full_name="Super Admin",
            email="super@eventpro.pe",
            phone="+519000000001",
            role=Role.SUPERADMIN,
            hashed_password="x",
        )
    )
    async with _client(web_app) as client:
        response = await client.patch(
            f"{PATH}/{ACTOR_ID}", headers=authorization(), json={"is_active": False}
        )
    assert response.status_code == 403
    assert ACTOR_ID not in web_app.state.tokens.revoked


async def test_patch_cannot_change_own_role(web_app: FastAPI) -> None:
    web_app.state.users.seed(
        User(
            id=ACTOR_ID,
            full_name="Super Admin",
            email="super@eventpro.pe",
            phone="+519000000001",
            role=Role.SUPERADMIN,
            hashed_password="x",
        )
    )
    async with _client(web_app) as client:
        demoted = await client.patch(
            f"{PATH}/{ACTOR_ID}", headers=authorization(), json={"role": "OPERADOR"}
        )
    assert demoted.status_code == 403


async def test_patch_unknown_user_returns_404(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        response = await client.patch(
            f"{PATH}/{uuid4()}", headers=authorization(), json={"is_active": False}
        )
    assert response.status_code == 404


async def test_patch_duplicate_phone_returns_409(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        first = await client.post(PATH, headers=authorization(), json=payload())
        second = await client.post(
            PATH,
            headers=authorization(),
            json=payload(email="otro@eventpro.pe", phone="+519111222999"),
        )
        response = await client.patch(
            f"{PATH}/{second.json()['id']}",
            headers=authorization(),
            json={"phone": first.json()["phone"]},
        )
    assert response.status_code == 409


async def test_patch_without_fields_returns_422(web_app: FastAPI) -> None:
    async with _client(web_app) as client:
        created = await client.post(PATH, headers=authorization(), json=payload())
        response = await client.patch(
            f"{PATH}/{created.json()['id']}", headers=authorization(), json={}
        )
    assert response.status_code == 422


async def test_token_of_unknown_account_gets_401(web_app: FastAPI) -> None:
    token = create_access_token(
        subject=str(uuid4()), role=Role.SUPERADMIN.value, secret_key=get_settings().secret_key
    )
    async with _client(web_app) as client:
        response = await client.get(PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_deactivated_account_gets_401(web_app: FastAPI) -> None:
    web_app.state.users.seed(
        User(
            id=ACTOR_ID,
            full_name="Super Admin",
            email="super@eventpro.pe",
            phone="+519000000001",
            role=Role.SUPERADMIN,
            hashed_password="x",
            is_active=False,
        )
    )
    async with _client(web_app) as client:
        response = await client.get(PATH, headers=authorization())
    assert response.status_code == 401


async def test_role_comes_from_database_not_token_claim(web_app: FastAPI) -> None:
    set_role(Role.OPERADOR)
    token = create_access_token(
        subject=str(ACTOR_ID), role=Role.SUPERADMIN.value, secret_key=get_settings().secret_key
    )
    async with _client(web_app) as client:
        response = await client.get(PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def _superadmin(**overrides: object) -> User:
    body: dict[str, object] = {
        "id": uuid4(),
        "full_name": "Super Admin",
        "email": "admin@eventpro.pe",
        "phone": "+519000000009",
        "role": Role.SUPERADMIN,
        "hashed_password": "x",
    }
    body.update(overrides)
    return User(**body)  # type: ignore[arg-type]


async def test_patch_last_superadmin_returns_422(web_app: FastAPI) -> None:
    target = web_app.state.users.seed(_superadmin(email="unico@eventpro.pe"))
    async with _client(web_app) as client:
        response = await client.patch(
            f"{PATH}/{target.id}", headers=authorization(), json={"role": "OPERADOR"}
        )
        detail = await client.get(f"{PATH}/{target.id}", headers=authorization())
    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-error")
    assert response.json()["detail"] == LAST_SUPERADMIN_MESSAGE
    assert detail.json()["role"] == "SUPERADMIN"


async def test_patch_demotes_superadmin_when_another_active_remains(web_app: FastAPI) -> None:
    target = web_app.state.users.seed(_superadmin(email="uno@eventpro.pe"))
    web_app.state.users.seed(_superadmin(email="dos@eventpro.pe", phone="+519000000002"))
    async with _client(web_app) as client:
        response = await client.patch(
            f"{PATH}/{target.id}", headers=authorization(), json={"role": "ENCARGADO"}
        )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "ENCARGADO"


async def test_patch_demotion_ignores_inactive_superadmins(web_app: FastAPI) -> None:
    target = web_app.state.users.seed(_superadmin(email="activo@eventpro.pe"))
    web_app.state.users.seed(
        _superadmin(email="inactivo@eventpro.pe", phone="+519000000003", is_active=False)
    )
    async with _client(web_app) as client:
        response = await client.patch(
            f"{PATH}/{target.id}", headers=authorization(), json={"role": "ENCARGADO"}
        )
    assert response.status_code == 422
    assert response.json()["detail"] == LAST_SUPERADMIN_MESSAGE
