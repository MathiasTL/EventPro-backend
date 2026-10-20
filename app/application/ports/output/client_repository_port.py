from typing import Protocol
from uuid import UUID

from app.domain.entities.client import Client


class IClientRepositoryPort(Protocol):
    """Persistencia de Client. Nunca confirma (``commit``): la transacción es del llamador."""

    async def get_by_id(self, client_id: UUID) -> Client | None:
        """Devuelve el cliente o None."""

    async def get_by_phone(self, phone: str) -> Client | None:
        """Busca por teléfono en cualquier formato que acepte PhoneNumber."""

    async def get_or_create(self, phone: str, full_name: str) -> Client:
        """Devuelve el cliente del teléfono o lo crea; nunca sobrescribe el nombre existente."""
