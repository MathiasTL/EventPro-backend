"""Repositorio de vínculos de conversación con SQLAlchemy. No confirma (``commit``)."""

from collections.abc import Collection, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.conversation_link import ConversationLink
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.infrastructure.adapters.secondary.persistence.mappers.conversation_link_mapper import (
    apply_conversation_link_to_model,
    conversation_link_to_domain,
)
from app.infrastructure.adapters.secondary.persistence.models.conversation_link_model import (
    ConversationLinkModel,
)


class SqlAlchemyConversationLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(
        self, conversation_id: int, client_id: UUID | None, now: datetime
    ) -> ConversationLink:
        await self._session.execute(
            pg_insert(ConversationLinkModel)
            .values(
                id=uuid4(),
                chatwoot_conversation_id=conversation_id,
                client_id=client_id,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["chatwoot_conversation_id"])
        )
        link = await self.get(conversation_id)
        if link is None:  # pragma: no cover - ON CONFLICT garantiza que la fila existe
            raise RuntimeError("El vínculo no existe tras el upsert")
        return link

    async def get(self, conversation_id: int) -> ConversationLink | None:
        row = await self._session.scalar(
            select(ConversationLinkModel)
            .where(ConversationLinkModel.chatwoot_conversation_id == conversation_id)
            .execution_options(populate_existing=True)
        )
        return conversation_link_to_domain(row) if row is not None else None

    async def get_many(self, conversation_ids: Collection[int]) -> Sequence[ConversationLink]:
        if not conversation_ids:
            return []
        rows = await self._session.scalars(
            select(ConversationLinkModel)
            .where(ConversationLinkModel.chatwoot_conversation_id.in_(conversation_ids))
            .execution_options(populate_existing=True)
        )
        return [conversation_link_to_domain(row) for row in rows]

    async def save(self, link: ConversationLink) -> ConversationLink:
        row = await self._session.get(ConversationLinkModel, link.id)
        if row is None:
            raise ResourceNotFoundError(f"El vínculo {link.id} no existe")
        apply_conversation_link_to_model(row, link)
        await self._session.flush()
        return link

    async def claim(
        self, conversation_id: int, user_id: UUID, expected_assignee: UUID | None
    ) -> bool:
        return await self._compare_and_set(conversation_id, user_id, expected_assignee)

    async def release(self, conversation_id: int, expected_assignee: UUID) -> bool:
        return await self._compare_and_set(conversation_id, None, expected_assignee)

    async def _compare_and_set(
        self, conversation_id: int, new_assignee: UUID | None, expected_assignee: UUID | None
    ) -> bool:
        """UPDATE condicional en una sola sentencia: gana quien encuentra el asignado esperado."""

        current = ConversationLinkModel.assigned_user_id
        won = await self._session.scalar(
            update(ConversationLinkModel)
            .where(
                ConversationLinkModel.chatwoot_conversation_id == conversation_id,
                current.is_(None) if expected_assignee is None else current == expected_assignee,
            )
            .values(assigned_user_id=new_assignee, updated_at=func.now())
            .returning(ConversationLinkModel.id)
            .execution_options(synchronize_session=False)
        )
        return won is not None
