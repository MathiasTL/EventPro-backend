from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.entities.conversation_link import ConversationLink


class IConversationLinkRepositoryPort(Protocol):
    """Persistencia de ConversationLink. Nunca confirma: la transacción es del llamador.

    La asignación solo cambia con ``claim`` y ``release``; ``save`` no la toca, para que un
    guardado con datos viejos (por ejemplo, el bot) no pise la toma de un encargado.
    """

    async def ensure(
        self, conversation_id: int, client_id: UUID | None, now: datetime
    ) -> ConversationLink:
        """Crea el vínculo si falta y lo devuelve; seguro ante dos escritores simultáneos."""

    async def get(self, conversation_id: int) -> ConversationLink | None:
        """Devuelve el vínculo por el id de la conversación en Chatwoot, o None."""

    async def get_many(self, conversation_ids: Collection[int]) -> Sequence[ConversationLink]:
        """Devuelve los vínculos existentes del lote (los ausentes se omiten)."""

    async def save(self, link: ConversationLink) -> ConversationLink:
        """Persiste los cambios (sin la asignación); lanza ResourceNotFoundError si no existe."""

    async def claim(
        self, conversation_id: int, user_id: UUID, expected_assignee: UUID | None
    ) -> bool:
        """*Compare-and-set* de la asignación: ``True`` solo si el asignado era el esperado."""

    async def release(self, conversation_id: int, expected_assignee: UUID) -> bool:
        """Limpia la asignación con la misma condición; ``True`` solo si la liberó."""
