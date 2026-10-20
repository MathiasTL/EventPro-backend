from datetime import UTC, datetime

from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.auth.dto import AuthSession
from app.application.use_cases.auth.errors import InvalidCredentialsError, UserInactiveError
from app.application.use_cases.auth.issuer import build_session
from app.core.security import hash_refresh_token


class RefreshUseCase:
    def __init__(
        self,
        users: IUserRepositoryPort,
        tokens: IRefreshTokenRepositoryPort,
        *,
        secret_key: str,
        access_expire_minutes: int,
        refresh_expire_days: int,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._secret_key = secret_key
        self._access_expire_minutes = access_expire_minutes
        self._refresh_expire_days = refresh_expire_days

    async def execute(self, refresh_token: str) -> AuthSession:
        record = await self._tokens.get_by_hash(hash_refresh_token(refresh_token))
        if record is None or not record.is_valid(datetime.now(UTC)):
            raise InvalidCredentialsError
        user = await self._users.get_by_id(record.user_id)
        if user is None:
            raise InvalidCredentialsError
        if not user.is_active:
            raise UserInactiveError
        session, new_record = build_session(
            user,
            secret_key=self._secret_key,
            access_expire_minutes=self._access_expire_minutes,
            refresh_expire_days=self._refresh_expire_days,
        )
        # Revocación del anterior + alta del nuevo en una transacción serializada con
        # las mutaciones del usuario: un PATCH concurrente (cambio de contraseña,
        # desactivación) no puede dejar un refresh token nuevo sin revocar.
        if not await self._tokens.rotate(record.token_hash, new_record, datetime.now(UTC)):
            raise InvalidCredentialsError
        return session
