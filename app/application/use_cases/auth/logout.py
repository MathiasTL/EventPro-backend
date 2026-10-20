from uuid import UUID

from app.application.ports.output.refresh_token_repository_port import IRefreshTokenRepositoryPort
from app.core.security import hash_refresh_token


class LogoutUseCase:
    def __init__(self, tokens: IRefreshTokenRepositoryPort) -> None:
        self._tokens = tokens

    async def execute(self, user_id: UUID, refresh_token: str) -> None:
        """Revoca el refresh token del usuario. Idempotente: repetir no falla."""
        record = await self._tokens.get_by_hash(hash_refresh_token(refresh_token))
        if record is not None and record.user_id == user_id and not record.is_revoked:
            await self._tokens.revoke(record.token_hash)
