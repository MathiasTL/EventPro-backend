"""Unidad de trabajo de los eventos de mensaje de la bandeja (spec 09, sección 6.1).

El vínculo de la conversación, la búsqueda de cliente y la búsqueda del *outbox* comparten
una transacción corta que confirma al salir sin error.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from app.application.ports.output.client_repository_port import IClientRepositoryPort
from app.application.ports.output.conversation_link_repository_port import (
    IConversationLinkRepositoryPort,
)
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort


@dataclass(frozen=True)
class InboxEventTransaction:
    outbox: IOutboxRepositoryPort
    links: IConversationLinkRepositoryPort
    clients: IClientRepositoryPort


InboxEventUnitOfWork = Callable[[], AbstractAsyncContextManager[InboxEventTransaction]]
