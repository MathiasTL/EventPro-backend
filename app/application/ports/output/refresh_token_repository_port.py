from datetime import datetime
from typing import Protocol

from app.domain.entities.refresh_token import RefreshToken


class IRefreshTokenRepositoryPort(Protocol):
    async def add(self, token: RefreshToken) -> None:
        """Persiste un refresh token nuevo (solo se guarda su hash)."""

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Refresh token por hash SHA-256; None si no existe."""

    async def revoke(self, token_hash: str) -> bool:
        """Revoca el token solo si seguía vigente (no revocado).

        Devuelve True si esta llamada lo revocó; False si no existe o ya estaba
        revocado (p. ej. por una revocación concurrente).
        """

    async def rotate(self, old_token_hash: str, new_token: RefreshToken, now: datetime) -> bool:
        """Rota atómicamente: revoca el token anterior y persiste el nuevo.

        Serializa con las mutaciones del usuario (bloquea su fila) y solo procede
        si el token anterior sigue vigente y el usuario sigue activo. Devuelve
        False, sin persistir nada, si el token ya fue revocado o expiró, o si la
        cuenta fue desactivada o eliminada.
        """
