"""Caso de uso EnqueueMessage: encola un mensaje saliente en la transacción del llamador."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.value_objects.outbox import DEFAULT_MAX_ATTEMPTS, MessageType
from app.domain.value_objects.phone_number import PhoneNumber


class EnqueueMessage:
    """Agrega el mensaje con la sesión del llamador; no hace ``commit``.

    El mensaje se guarda o se descarta junto con la operación de negocio que lo originó.
    """

    def __init__(
        self,
        repository: IOutboxRepositoryPort,
        clock: IClockPort,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._max_attempts = max_attempts

    async def execute(
        self,
        *,
        recipient: PhoneNumber,
        message_type: MessageType,
        payload: Mapping[str, Any],
        redact_after_send: bool = False,
        author_user_id: UUID | None = None,
    ) -> OutboxMessage:
        message = OutboxMessage.create(
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            redact_after_send=redact_after_send,
            author_user_id=author_user_id,
            max_attempts=self._max_attempts,
            now=self._clock.utcnow(),
        )
        return await self._repository.add(message)
