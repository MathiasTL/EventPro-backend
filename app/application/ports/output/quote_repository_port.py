from typing import Protocol
from uuid import UUID

from app.domain.entities.quote import Quote


class IQuoteRepositoryPort(Protocol):
    """Persistencia de Quote. Nunca confirma (``commit``): la transacción es del llamador."""

    async def add(self, quote: Quote) -> Quote:
        """Inserta una cotización nueva con sus extras; falla si el id o el hash ya existen."""

    async def save(self, quote: Quote) -> Quote:
        """Actualiza una cotización existente; lanza ResourceNotFoundError si no existe.

        Solo persiste el estado y los campos de ciclo de vida; no persiste cambios en ``extras``
        (los extras se escriben una sola vez en ``add``).
        """

    async def get_by_id(self, quote_id: UUID) -> Quote | None:
        """Devuelve la cotización con sus extras, o None."""
