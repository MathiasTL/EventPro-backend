from typing import Protocol
from uuid import UUID

from app.domain.entities.refresh_token import RefreshToken


class IRefreshTokenRepositoryPort(Protocol):
    async def add(self, token: RefreshToken) -> None:
        """Persiste un refresh token nuevo (solo se guarda su hash)."""

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Refresh token por hash SHA-256; None si no existe."""

    async def revoke(self, token_hash: str) -> None:
        """Marca el refresh token como revocado (is_revoked = true)."""

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """Revoca todos los refresh tokens vigentes del usuario (US-23)."""
