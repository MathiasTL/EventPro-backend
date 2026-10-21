"""El doble en memoria debe comportarse como el repositorio SQL (CAS y ensure idempotente)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities.conversation_link import ConversationLink
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from tests.application.conversation_link_support import InMemoryConversationLinkRepository

NOW = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


async def test_ensure_is_idempotent_and_returns_copies() -> None:
    repository = InMemoryConversationLinkRepository()
    first = await repository.ensure(1, None, NOW)
    first.client_id = uuid4()
    second = await repository.ensure(1, None, NOW)

    assert second.id == first.id
    assert second.client_id is None
    assert [link.id for link in await repository.get_many([1, 2])] == [first.id]


async def test_claim_and_release_follow_compare_and_set() -> None:
    repository = InMemoryConversationLinkRepository()
    await repository.ensure(1, None, NOW)
    first, second = uuid4(), uuid4()

    assert await repository.claim(1, first, None) is True
    assert await repository.claim(1, second, None) is False
    assert await repository.release(1, second) is False
    assert await repository.release(1, first) is True
    assert await repository.claim(9, first, None) is False
    link = await repository.get(1)
    assert link is not None
    assert link.assigned_user_id is None


async def test_save_keeps_the_stored_assignment_and_rejects_unknown_links() -> None:
    repository = InMemoryConversationLinkRepository()
    stale = await repository.ensure(1, None, NOW)
    owner = uuid4()
    await repository.claim(1, owner, None)
    stale.record_client_message(NOW)

    await repository.save(stale)

    stored = await repository.get(1)
    assert stored is not None
    assert stored.assigned_user_id == owner
    assert stored.last_client_message_at == NOW
    with pytest.raises(ResourceNotFoundError):
        await repository.save(ConversationLink.create(chatwoot_conversation_id=2, now=NOW))
