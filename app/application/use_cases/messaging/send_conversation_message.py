"""Enviar y reintentar un mensaje desde la bandeja (spec 09, 6.4 y 6.7).

Ambos casos encolan o reencolan en la sesión del llamador y auditan en esa misma sesión: el
mensaje y su auditoría se confirman o se descartan juntos. El eco y la entrega llegan después
por el worker (6.1), así que no se publica ningún evento aquí.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.application.dtos.messaging_dto import ConversationLifecycle, ConversationSummary
from app.application.ports.output.conversation_link_repository_port import (
    IConversationLinkRepositoryPort,
)
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.application.services.audit_service import AuditService
from app.application.use_cases.messaging.conversation_events import SERVICE_WINDOW
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.application.use_cases.messaging.retry_message import RetryMessage
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.exceptions.messaging_exceptions import (
    ConversationNotTakenError,
    ConversationTakenByOtherError,
    ConversationWindowClosedError,
)
from app.domain.exceptions.outbox_exceptions import (
    InvalidOutboxStateError,
    OutboxMessageNotFoundError,
)
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import MessageType

SEND_ACTION = "SEND_CONVERSATION_MESSAGE"
_ENTITY_NAME = "outbox_message"


@dataclass(frozen=True)
class QueuedMessage:
    outbox_id: UUID
    chatwoot_conversation_id: int


class _OutgoingFlow:
    """Precondiciones comunes de 6.4: tomada por el usuario y ventana de 24 h abierta."""

    def __init__(
        self,
        messaging: IMessagingPort,
        links: IConversationLinkRepositoryPort,
        outbox: IOutboxRepositoryPort,
        audit: AuditService,
    ) -> None:
        self._messaging = messaging
        self._links = links
        self._outbox = outbox
        self._audit = audit

    async def _authorize(self, conversation_id: int, user_id: UUID) -> ConversationSummary:
        """Lanza ``ConversationNotTakenError`` o ``ConversationTakenByOtherError``."""

        summary = await self._messaging.get_conversation(conversation_id)
        link = await self._links.get(conversation_id)
        assignee = link.assigned_user_id if link else None
        if summary.lifecycle is not ConversationLifecycle.OPEN or assignee is None:
            raise ConversationNotTakenError("Primero hay que tomar la conversación.")
        if assignee != user_id:
            raise ConversationTakenByOtherError(assignee)
        return summary

    async def _require_open_window(self, summary: ConversationSummary) -> None:
        if summary.service_window_open:
            return
        link = await self._links.get(summary.conversation_id)
        expires_at: datetime | None = None
        if link is not None and link.last_client_message_at is not None:
            expires_at = link.last_client_message_at + SERVICE_WINDOW
        raise ConversationWindowClosedError(expires_at)

    async def _record(self, message: OutboxMessage, user_id: UUID, **extra: object) -> None:
        """Sin contenido: solo el id de la conversación y el tipo (D9, sección 11)."""

        await self._audit.record(
            action=SEND_ACTION,
            entity_name=_ENTITY_NAME,
            entity_id=message.id,
            user_id=user_id,
            new_values={"message_type": message.message_type.value, **extra},
        )


class SendConversationMessage(_OutgoingFlow):
    def __init__(
        self,
        messaging: IMessagingPort,
        links: IConversationLinkRepositoryPort,
        outbox: IOutboxRepositoryPort,
        audit: AuditService,
        enqueue: EnqueueMessage,
    ) -> None:
        super().__init__(messaging, links, outbox, audit)
        self._enqueue = enqueue

    async def execute(
        self,
        conversation_id: int,
        *,
        user_id: UUID,
        content: str | None = None,
        document: Mapping[str, Any] | None = None,
    ) -> QueuedMessage:
        """Encola texto (``content``) o un documento (``document``, forma de ``DOCUMENT``).

        Lanza ``ConversationNotTakenError``, ``ConversationTakenByOtherError``,
        ``ConversationWindowClosedError``, ``ValidationError`` o, si Chatwoot falla,
        ``ResourceNotFoundError`` / ``MessagingUnavailableError``. Responder no cambia la
        asignación.
        """

        if (content is None or not content.strip()) == (document is None):
            raise ValidationError("El mensaje debe incluir texto o un documento, no ambos.")
        summary = await self._authorize(conversation_id, user_id)
        await self._require_open_window(summary)
        if document is not None:
            message_type = MessageType.DOCUMENT
            payload: Mapping[str, Any] = document
        else:
            message_type = MessageType.TEXT
            payload = {"body": content}
        message = await self._enqueue.execute(
            recipient=summary.phone,
            message_type=message_type,
            payload=payload,
            author_user_id=user_id,
        )
        await self._record(message, user_id, conversation_id=conversation_id)
        return QueuedMessage(message.id, conversation_id)


class RetryConversationMessage(_OutgoingFlow):
    def __init__(
        self,
        messaging: IMessagingPort,
        links: IConversationLinkRepositoryPort,
        outbox: IOutboxRepositoryPort,
        audit: AuditService,
        retry: RetryMessage,
    ) -> None:
        super().__init__(messaging, links, outbox, audit)
        self._retry = retry

    async def execute(
        self, conversation_id: int, outbox_id: UUID, *, user_id: UUID
    ) -> QueuedMessage:
        """Reencola la misma fila (D6). Lanza lo de ``SendConversationMessage`` más
        ``OutboxMessageNotFoundError`` (fila inexistente o de otro destinatario) e
        ``InvalidOutboxStateError`` (no fallida o sin contenido).
        """

        summary = await self._authorize(conversation_id, user_id)
        message = await self._outbox.get_by_id(outbox_id, for_update=True)
        if message is None or message.recipient != summary.phone:
            raise OutboxMessageNotFoundError("El mensaje no existe en esta conversación.")
        if not message.is_retryable:
            raise InvalidOutboxStateError(
                "Solo se puede reintentar un mensaje fallido que conserve su contenido."
            )
        await self._require_open_window(summary)
        await self._retry.execute(outbox_id)
        await self._record(
            message, user_id, conversation_id=conversation_id, retry_of=str(outbox_id)
        )
        return QueuedMessage(outbox_id, conversation_id)
