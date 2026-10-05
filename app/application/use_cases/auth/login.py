from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.application.ports.output.user_repository_port import IUserRepositoryPort
from app.application.use_cases.auth.dto import AuthSession
from app.application.use_cases.auth.errors import InvalidCredentialsError, UserInactiveError
from app.application.use_cases.auth.issuer import issue_session
from app.core.security import verify_password


class LoginUseCase:
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

    async def execute(self, email: str, password: str) -> AuthSession:
        user = await self._users.get_by_email(email.strip())
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError
        if not user.is_active:
            raise UserInactiveError
        return await issue_session(
            self._tokens,
            user,
            secret_key=self._secret_key,
            access_expire_minutes=self._access_expire_minutes,
            refresh_expire_days=self._refresh_expire_days,
        )
