"""Dobles de tomar y devolver: unidad de trabajo en memoria y auditoría que guarda entradas."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.dtos.messaging_dto import ConversationStatus
from app.application.ports.output.conversation_link_repository_port import (
    IConversationLinkRepositoryPort,
)
from app.application.services.audit_service import AuditService
from app.application.use_cases.messaging.conversation_assignment import (
    ReleaseConversation,
    TakeoverConversation,
)
from app.application.use_cases.messaging.conversation_views import ConversationViewBuilder
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.conversation_link import ConversationLink, HandoffReason
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.cache.in_memory_conversation_session_adapter import (
    InMemoryConversationSessionAdapter,
)
from app.infrastructure.adapters.secondary.events.in_memory_conversation_event_publisher import (
    InMemoryConversationEventPublisher,
)
from app.infrastructure.adapters.secondary.external_services.fake_messaging_adapter import (
    FakeMessagingAdapter,
)
from tests.application.conversation_link_support import InMemoryConversationLinkRepository
from tests.application.inbox_read_support import FakeInboxLookup
from tests.application.outbox_support import FixedClock

NOW = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
PHONE = PhoneNumber("+51999888777")


class InMemoryAuditPort:
    def __init__(self) -> None:
        self.entries: list[AuditLog] = []

    async def record(self, entry: AuditLog) -> None:
        self.entries.append(entry)


class InMemoryLinkUnitOfWork:
    def __init__(self, links: InMemoryConversationLinkRepository) -> None:
        self._links = links
        self.opened = 0

    def __call__(self) -> AbstractAsyncContextManager[IConversationLinkRepositoryPort]:
        return self._open()

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[IConversationLinkRepositoryPort]:
        self.opened += 1
        yield self._links


class AssignmentWorld:
    """Una conversación (id 1) en ``pending`` con el bot, más los puertos de tomar y devolver."""

    conversation_id = 1

    def __init__(self) -> None:
        self.messaging = FakeMessagingAdapter()
        self.messaging.receive_text(PHONE, "Hola", name="Carlos")
        self.links = InMemoryConversationLinkRepository()
        self.uow = InMemoryLinkUnitOfWork(self.links)
        self.sessions = InMemoryConversationSessionAdapter()
        self.audit_port = InMemoryAuditPort()
        self.publisher = InMemoryConversationEventPublisher()
        self.lookup = FakeInboxLookup()
        views = ConversationViewBuilder(self.links, self.lookup)
        args = (
            self.messaging,
            self.uow,
            views,
            self.sessions,
            AuditService(self.audit_port),
            self.publisher,
            FixedClock(NOW),
        )
        self.takeover = TakeoverConversation(*args)
        self.release = ReleaseConversation(*args)

    async def open_unassigned(self, reason: HandoffReason = HandoffReason.CLIENT_REQUEST) -> None:
        """Derivación del bot sin tomar: ``open`` y sin asignado, con su motivo."""

        link = ConversationLink.create(chatwoot_conversation_id=self.conversation_id, now=NOW)
        link.register_handoff(reason=reason, summary=None, at=NOW)
        self.links.put(link)
        await self.messaging.set_conversation_status(self.conversation_id, ConversationStatus.HUMAN)

    async def assign(self, user_id: UUID) -> None:
        if self.conversation_id not in self.links.links:
            await self.open_unassigned()
        assert await self.links.claim(self.conversation_id, user_id, None)

    def stored(self) -> ConversationLink:
        return self.links.links[self.conversation_id]


def new_user() -> UUID:
    return uuid4()
