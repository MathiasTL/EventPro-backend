"""Doble en memoria de ``IConversationLinkRepositoryPort`` para pruebas de casos de uso."""

from collections.abc import Collection, Sequence
from copy import deepcopy
from datetime import datetime
from uuid import UUID

from app.domain.entities.conversation_link import ConversationLink
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class InMemoryConversationLinkRepository:
    """Guarda copias, como una base de datos; ``claim`` y ``release`` replican el CAS real."""

    def __init__(self) -> None:
        self.links: dict[int, ConversationLink] = {}

    def put(self, link: ConversationLink) -> ConversationLink:
        self.links[link.chatwoot_conversation_id] = deepcopy(link)
        return link

    async def ensure(
        self, conversation_id: int, client_id: UUID | None, now: datetime
    ) -> ConversationLink:
        if conversation_id not in self.links:
            self.links[conversation_id] = ConversationLink.create(
                chatwoot_conversation_id=conversation_id, client_id=client_id, now=now
            )
        return deepcopy(self.links[conversation_id])

    async def get(self, conversation_id: int) -> ConversationLink | None:
        found = self.links.get(conversation_id)
        return deepcopy(found) if found is not None else None

    async def get_many(self, conversation_ids: Collection[int]) -> Sequence[ConversationLink]:
        return [deepcopy(self.links[i]) for i in conversation_ids if i in self.links]

    async def save(self, link: ConversationLink) -> ConversationLink:
        stored = self.links.get(link.chatwoot_conversation_id)
        if stored is None or stored.id != link.id:
            raise ResourceNotFoundError(f"El vínculo {link.id} no existe")
        assigned = stored.assigned_user_id  # la asignación solo cambia con claim/release
        updated = deepcopy(link)
        updated.assigned_user_id = assigned
        self.links[link.chatwoot_conversation_id] = updated
        return link

    async def claim(
        self, conversation_id: int, user_id: UUID, expected_assignee: UUID | None
    ) -> bool:
        stored = self.links.get(conversation_id)
        if stored is None or stored.assigned_user_id != expected_assignee:
            return False
        stored.assigned_user_id = user_id
        return True

    async def release(self, conversation_id: int, expected_assignee: UUID) -> bool:
        stored = self.links.get(conversation_id)
        if stored is None or stored.assigned_user_id != expected_assignee:
            return False
        stored.assigned_user_id = None
        return True
