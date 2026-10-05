from typing import Protocol
from uuid import UUID

from app.domain.entities.user import User


class IUserRepositoryPort(Protocol):
    async def get_by_email(self, email: str) -> User | None:
        """Usuario por correo (case-insensitive); None si no existe."""

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Usuario por identificador; None si no existe."""
