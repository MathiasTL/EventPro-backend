"""Caso de uso RetryMessage: reencola un mensaje con envío o entrega fallidos."""

from uuid import UUID

from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class RetryMessage:
    """Aplica ``retry`` a un mensaje existente; no hace ``commit``."""

    def __init__(self, repository: IOutboxRepositoryPort, clock: IClockPort) -> None:
        self._repository = repository
        self._clock = clock

    async def execute(self, message_id: UUID) -> OutboxMessage:
        message = await self._repository.get_by_id(message_id, for_update=True)
        if message is None:
            raise ResourceNotFoundError(f"El mensaje {message_id} no existe")
        message.retry(now=self._clock.utcnow())
        return await self._repository.save(message)
