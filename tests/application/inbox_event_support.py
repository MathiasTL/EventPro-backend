"""Dobles en memoria de la unidad de trabajo de los eventos de la bandeja."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.application.ports.output.inbox_event_unit_of_work_port import InboxEventTransaction
from app.domain.entities.client import Client
from tests.application.conversation_link_support import InMemoryConversationLinkRepository
from tests.application.outbox_support import InMemoryOutboxStore


class InMemoryClients:
    """``IClientRepositoryPort`` de solo lectura; ``get_or_create`` falla: D1 no crea clientes."""

    def __init__(self, *clients: Client) -> None:
        self.clients = list(clients)

    async def get_by_id(self, client_id: UUID) -> Client | None:
        return next((c for c in self.clients if c.id == client_id), None)

    async def get_by_phone(self, phone: str) -> Client | None:
        return next((c for c in self.clients if c.phone.value == phone), None)

    async def get_or_create(self, phone: str, full_name: str) -> Client:
        raise AssertionError("La bandeja no crea clientes (D1)")


class InMemoryInbox:
    """``InboxEventUnitOfWork``: outbox transaccional más vínculos y clientes en memoria."""

    def __init__(
        self,
        store: InMemoryOutboxStore,
        links: InMemoryConversationLinkRepository | None = None,
        clients: InMemoryClients | None = None,
    ) -> None:
        self.store = store
        self.links = links or InMemoryConversationLinkRepository()
        self.clients = clients or InMemoryClients()

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[InboxEventTransaction]:
        async with self.store.transaction() as outbox:
            yield InboxEventTransaction(outbox=outbox, links=self.links, clients=self.clients)
