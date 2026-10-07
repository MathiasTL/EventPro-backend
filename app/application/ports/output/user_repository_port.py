from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.application.dtos.user_dto import UserFilters
from app.domain.entities.user import User


class IUserRepositoryPort(Protocol):
    async def get_by_email(self, email: str) -> User | None:
        """Usuario por correo (case-insensitive); None si no existe."""

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Usuario por identificador; None si no existe."""

    async def add(self, user: User) -> None:
        """Crea el usuario; DuplicateResourceError si correo o teléfono ya existen."""

    async def update(self, user: User) -> None:
        """Persiste los cambios; DuplicateResourceError si el teléfono ya existe."""

    async def list(self, filters: UserFilters) -> Sequence[User]:
        """Usuarios que cumplen los filtros, ordenados por nombre."""

    async def count(self, filters: UserFilters) -> int:
        """Total de usuarios que cumplen los filtros."""
