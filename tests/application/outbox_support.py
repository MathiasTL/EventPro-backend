"""Dobles en memoria de la cola de mensajes salientes para probar sin infraestructura."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID

from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.outbox import OutboxStatus
from tests.domain.outbox_support import NOW


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def utcnow(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now = self.now + delta


class InMemoryOutboxRepository:
    """Implementa ``IOutboxRepositoryPort`` sobre un diccionario; entrega copias, como una BD."""

    def __init__(self, messages: dict[UUID, OutboxMessage], fail_save: set[UUID]) -> None:
        self._messages = messages
        self._fail_save = fail_save
        self.for_update_requests = 0

    async def add(self, message: OutboxMessage) -> OutboxMessage:
        self._messages[message.id] = deepcopy(message)
        return message

    async def save(self, message: OutboxMessage) -> OutboxMessage:
        if message.id in self._fail_save:
            raise RuntimeError("Fallo simulado de persistencia")
        if message.id not in self._messages:
            raise ResourceNotFoundError(f"El mensaje {message.id} no existe")
        self._messages[message.id] = deepcopy(message)
        return message

    async def get_by_id(
        self, message_id: UUID, *, for_update: bool = False
    ) -> OutboxMessage | None:
        self.for_update_requests += int(for_update)
        found = self._messages.get(message_id)
        return deepcopy(found) if found is not None else None

    async def get_by_external_id(
        self, external_message_id: str, *, for_update: bool = False
    ) -> OutboxMessage | None:
        self.for_update_requests += int(for_update)
        for message in self._messages.values():
            if message.external_message_id == external_message_id:
                return deepcopy(message)
        return None

    async def claim_due(
        self, *, now: datetime, limit: int, lease: timedelta
    ) -> Sequence[OutboxMessage]:
        due = sorted(
            (
                message
                for message in self._messages.values()
                if message.status is OutboxStatus.PENDING and message.next_attempt_at <= now
            ),
            key=lambda message: (message.next_attempt_at, message.created_at),
        )[:limit]
        for message in due:
            message.next_attempt_at = now + lease
        return [deepcopy(message) for message in due]


class InMemoryOutboxStore:
    """Almacén con transacciones: confirma al salir sin error y descarta si el bloque falla."""

    def __init__(self) -> None:
        self.messages: dict[UUID, OutboxMessage] = {}
        self.fail_save: set[UUID] = set()
        self.commits = 0
        self.rollbacks = 0

    def repository(self) -> InMemoryOutboxRepository:
        """Repositorio que escribe directo, como una sesión del llamador sin cerrar."""

        return InMemoryOutboxRepository(self.messages, self.fail_save)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[IOutboxRepositoryPort]:
        working = deepcopy(self.messages)
        try:
            yield InMemoryOutboxRepository(working, self.fail_save)
        except BaseException:
            self.rollbacks += 1
            raise
        self.messages = working
        self.commits += 1

    def put(self, message: OutboxMessage) -> OutboxMessage:
        self.messages[message.id] = deepcopy(message)
        return message


class FakeDocumentSource:
    """``IDocumentSourcePort`` en memoria: ruta a bytes."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = files or {}
        self.reads: list[str] = []

    async def read(self, path: str) -> bytes:
        self.reads.append(path)
        if path not in self.files:
            raise ResourceNotFoundError("Documento no encontrado")
        return self.files[path]
