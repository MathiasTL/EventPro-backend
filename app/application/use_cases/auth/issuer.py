import uuid
from datetime import UTC, datetime, timedelta

from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.application.use_cases.auth.dto import AuthSession, UserInfo
from app.core.security import create_access_token, hash_refresh_token, new_refresh_token
from app.domain.entities.refresh_token import RefreshToken
from app.domain.entities.user import User


def build_session(
    user: User,
    *,
    secret_key: str,
    access_expire_minutes: int,
    refresh_expire_days: int,
) -> tuple[AuthSession, RefreshToken]:
    """Construye el par de tokens (access JWT + refresh) sin persistirlo."""
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        secret_key=secret_key,
        expires_minutes=access_expire_minutes,
    )
    plain_refresh = new_refresh_token()
    record = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_refresh_token(plain_refresh),
        expires_at=datetime.now(UTC) + timedelta(days=refresh_expire_days),
    )
    session = AuthSession(
        access_token=access_token,
        refresh_token=plain_refresh,
        expires_in=access_expire_minutes * 60,
        user=UserInfo(id=user.id, full_name=user.full_name, role=user.role),
    )
    return session, record


async def issue_session(
    tokens: IRefreshTokenRepositoryPort,
    user: User,
    *,
    secret_key: str,
    access_expire_minutes: int,
    refresh_expire_days: int,
) -> AuthSession:
    """Emite un par de tokens (access JWT + refresh rotativo persistido)."""
    session, record = build_session(
        user,
        secret_key=secret_key,
        access_expire_minutes=access_expire_minutes,
        refresh_expire_days=refresh_expire_days,
    )
    await tokens.add(record)
    return session
