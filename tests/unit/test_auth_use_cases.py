"""Casos de uso de autenticación con repositorios en memoria (sin base de datos)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application.use_cases.auth.errors import InvalidCredentialsError, UserInactiveError
from app.application.use_cases.auth.login import LoginUseCase
from app.application.use_cases.auth.logout import LogoutUseCase
from app.application.use_cases.auth.refresh import RefreshUseCase
from app.core.security import decode_access_token, hash_password, hash_refresh_token
from app.domain.entities.refresh_token import RefreshToken
from app.domain.entities.user import User
from app.domain.value_objects.role import Role

SECRET = "test-secret-key-0123456789abcdef0123456789"
PASSWORD = "PasswordSeguro123!"
_HASHED_PASSWORD = hash_password(PASSWORD)


class FakeUserRepository:
    def __init__(self, users: list[User]) -> None:
        self._by_id = {user.id: user for user in users}
        self._by_email = {user.email.lower(): user for user in users}

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email.strip().lower())

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self._tokens: dict[str, RefreshToken] = {}

    async def add(self, token: RefreshToken) -> None:
        self._tokens[token.token_hash] = token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return self._tokens.get(token_hash)

    async def revoke(self, token_hash: str) -> None:
        record = self._tokens.get(token_hash)
        if record is not None:
            record.is_revoked = True


def make_user(
    *,
    email: str = "juan@eventpro.pe",
    role: Role = Role.ENCARGADO,
    is_active: bool = True,
) -> User:
    return User(
        id=uuid.uuid4(),
        full_name="Juan Pérez",
        email=email,
        phone=f"+519{uuid.uuid4().hex[:8]}",
        role=role,
        hashed_password=_HASHED_PASSWORD,
        is_active=is_active,
    )


def make_login(users: FakeUserRepository, tokens: FakeRefreshTokenRepository) -> LoginUseCase:
    return LoginUseCase(
        users,
        tokens,
        secret_key=SECRET,
        access_expire_minutes=60,
        refresh_expire_days=7,
    )


async def test_login_ok_issues_token_pair_and_user_info() -> None:
    user = make_user()
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()

    session = await make_login(users, tokens).execute(user.email, PASSWORD)

    payload = decode_access_token(session.access_token, SECRET)
    assert payload["sub"] == str(user.id)
    assert payload["role"] == Role.ENCARGADO
    assert session.expires_in == 3600
    assert session.user is not None
    assert session.user.id == user.id
    assert session.user.role == Role.ENCARGADO
    stored = await tokens.get_by_hash(hash_refresh_token(session.refresh_token))
    assert stored is not None
    assert stored.user_id == user.id
    assert not stored.is_revoked


async def test_login_is_case_insensitive_on_email() -> None:
    user = make_user(email="Encargado@EventPro.pe")
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()

    session = await make_login(users, tokens).execute("  ENCARGADO@EVENTPRO.PE ", PASSWORD)
    assert session.user is not None
    assert session.user.id == user.id


@pytest.mark.parametrize(
    "email,password", [("nadie@eventpro.pe", PASSWORD), ("otro@eventpro.pe", "WrongPass123!")]
)
async def test_login_rejects_bad_credentials(email: str, password: str) -> None:
    user = make_user(email="otro@eventpro.pe")
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()

    with pytest.raises(InvalidCredentialsError):
        await make_login(users, tokens).execute(email, password)


async def test_login_rejects_inactive_user() -> None:
    user = make_user(is_active=False)
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()

    with pytest.raises(UserInactiveError):
        await make_login(users, tokens).execute(user.email, PASSWORD)


async def test_refresh_rotates_token_pair() -> None:
    user = make_user()
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()
    login = make_login(users, tokens)
    original = await login.execute(user.email, PASSWORD)

    refresh = RefreshUseCase(
        users,
        tokens,
        secret_key=SECRET,
        access_expire_minutes=60,
        refresh_expire_days=7,
    )
    rotated = await refresh.execute(original.refresh_token)

    assert rotated.refresh_token != original.refresh_token
    payload = decode_access_token(rotated.access_token, SECRET)
    assert payload["sub"] == str(user.id)
    old_record = await tokens.get_by_hash(hash_refresh_token(original.refresh_token))
    assert old_record is not None
    assert old_record.is_revoked
    new_record = await tokens.get_by_hash(hash_refresh_token(rotated.refresh_token))
    assert new_record is not None
    assert not new_record.is_revoked


async def test_refresh_rejects_revoked_token() -> None:
    user = make_user()
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()
    login = make_login(users, tokens)
    issued = await login.execute(user.email, PASSWORD)
    await tokens.revoke(hash_refresh_token(issued.refresh_token))

    refresh = RefreshUseCase(
        users,
        tokens,
        secret_key=SECRET,
        access_expire_minutes=60,
        refresh_expire_days=7,
    )
    with pytest.raises(InvalidCredentialsError):
        await refresh.execute(issued.refresh_token)


async def test_refresh_rejects_expired_token() -> None:
    user = make_user()
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()
    expired = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_refresh_token("token-expirado"),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    await tokens.add(expired)

    refresh = RefreshUseCase(
        users,
        tokens,
        secret_key=SECRET,
        access_expire_minutes=60,
        refresh_expire_days=7,
    )
    with pytest.raises(InvalidCredentialsError):
        await refresh.execute("token-expirado")


async def test_refresh_rejects_unknown_token() -> None:
    user = make_user()
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()

    refresh = RefreshUseCase(
        users,
        tokens,
        secret_key=SECRET,
        access_expire_minutes=60,
        refresh_expire_days=7,
    )
    with pytest.raises(InvalidCredentialsError):
        await refresh.execute("desconocido")


async def test_logout_revokes_own_token_and_is_idempotent() -> None:
    user = make_user()
    users = FakeUserRepository([user])
    tokens = FakeRefreshTokenRepository()
    issued = await make_login(users, tokens).execute(user.email, PASSWORD)
    logout = LogoutUseCase(tokens)

    await logout.execute(user.id, issued.refresh_token)
    await logout.execute(user.id, issued.refresh_token)

    record = await tokens.get_by_hash(hash_refresh_token(issued.refresh_token))
    assert record is not None
    assert record.is_revoked


async def test_logout_does_not_revoke_another_users_token() -> None:
    owner = make_user(email="owner@eventpro.pe")
    intruder = make_user(email="intruder@eventpro.pe")
    users = FakeUserRepository([owner, intruder])
    tokens = FakeRefreshTokenRepository()
    issued = await make_login(users, tokens).execute(owner.email, PASSWORD)
    logout = LogoutUseCase(tokens)

    await logout.execute(intruder.id, issued.refresh_token)

    record = await tokens.get_by_hash(hash_refresh_token(issued.refresh_token))
    assert record is not None
    assert not record.is_revoked
