"""Hilo de una conversación (spec 09, 7.3): mensajes de Chatwoot más autoría y reintento del outbox.

Todo el hilo se arma con una lectura de mensajes, una del outbox y una de nombres de usuario.
"""

from collections.abc import Mapping
from uuid import UUID

from app.application.dtos.inbox_dto import (
    MessageAttachmentView,
    MessagePage,
    MessageView,
    UnsentMessageView,
)
from app.application.dtos.messaging_dto import AuthorType, ConversationMessage, MessageDirection
from app.application.ports.output.inbox_lookup_port import IInboxLookupPort
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.ports.output.outbox_repository_port import IOutboxRepositoryPort
from app.application.use_cases.messaging.conversation_events import is_retryable
from app.application.use_cases.messaging.failure_catalog import (
    translate_delivery_failure,
    translate_send_failure,
)
from app.application.use_cases.messaging.message_authorship import resolve_author_type
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.value_objects.outbox import DeliveryStatus, OutboxStatus

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
_DELIVERY_STATUSES = {
    "sent": "SENT",
    "delivered": "DELIVERED",
    "read": "READ",
    "failed": "FAILED",
}


class ListConversationMessages:
    def __init__(
        self,
        messaging: IMessagingPort,
        outbox: IOutboxRepositoryPort,
        lookup: IInboxLookupPort,
    ) -> None:
        self._messaging = messaging
        self._outbox = outbox
        self._lookup = lookup

    async def execute(
        self, conversation_id: int, *, before_id: int | None = None, limit: int = DEFAULT_LIMIT
    ) -> MessagePage:
        """Del más reciente al más antiguo; ``unsent`` solo sin ``before_id`` (primera página).

        Lanza ``ResourceNotFoundError`` si la conversación no existe.
        """

        first_page = before_id is None
        summary = await self._messaging.get_conversation(conversation_id) if first_page else None
        # Una más que el límite revela si hay mensajes anteriores.
        fetched = await self._messaging.list_messages(
            conversation_id, before_id=before_id, limit=limit + 1
        )
        has_more = len(fetched) > limit
        newest_first = list(reversed(fetched[-limit:])) if limit > 0 else []

        references = {
            m.message_id for m in newest_first if m.direction is MessageDirection.OUTGOING
        }
        rows = await self._outbox.get_many_by_external_ids(references) if references else {}
        unsent = (
            await self._outbox.list_unsent_for_recipient(summary.phone)
            if summary is not None
            else None
        )
        authors = {
            row.author_user_id
            for row in [*rows.values(), *(unsent or ())]
            if row.author_user_id is not None
        }
        names = await self._lookup.user_names(authors) if authors else {}

        return MessagePage(
            items=[_message_view(m, rows.get(m.message_id), names) for m in newest_first],
            has_more=has_more,
            unsent=None if unsent is None else [_unsent_view(row, names) for row in unsent],
        )


def _message_view(
    message: ConversationMessage, outbox: OutboxMessage | None, names: Mapping[UUID, str]
) -> MessageView:
    author = resolve_author_type(direction=message.direction, outbox=outbox, sender=message.sender)
    delivery = _delivery_status(message, outbox)
    failure = (
        translate_delivery_failure(
            message.external_error or (outbox.delivery_error if outbox else None)
        )
        if delivery == DeliveryStatus.FAILED.value
        else None
    )
    return MessageView(
        id=int(message.message_id) if message.message_id.isdecimal() else message.message_id,
        direction=message.direction,
        author_type=author,
        author_name=_author_name(author, message, outbox, names),
        content=message.body or "",
        attachments=[
            MessageAttachmentView(a.attachment_id, a.file_type, a.content_type)
            for a in message.attachments
        ],
        delivery_status=delivery,
        failure_reason=failure.reason if failure else None,
        failure_code=failure.code if failure else None,
        outbox_id=outbox.id if outbox else None,
        retryable=is_retryable(outbox),
        created_at=message.sent_at,
    )


def _author_name(
    author: AuthorType | None,
    message: ConversationMessage,
    outbox: OutboxMessage | None,
    names: Mapping[UUID, str],
) -> str | None:
    """Solo los encargados llevan nombre: el del usuario del outbox o, sin fila, el de Chatwoot."""

    if author is not AuthorType.AGENT:
        return None
    if outbox is not None and outbox.author_user_id is not None:
        return names.get(outbox.author_user_id)
    return message.sender_name


def _delivery_status(message: ConversationMessage, outbox: OutboxMessage | None) -> str | None:
    """El estado sale de Chatwoot; sin él, del outbox, y si tampoco, ``SENT``."""

    if message.direction is not MessageDirection.OUTGOING:
        return None
    reported = _DELIVERY_STATUSES.get((message.status or "").lower())
    if reported is not None:
        return reported
    if outbox is not None and outbox.delivery_status is not None:
        return outbox.delivery_status.value
    return "SENT"


def _unsent_view(row: OutboxMessage, names: Mapping[UUID, str]) -> UnsentMessageView:
    failed = row.status is OutboxStatus.FAILED
    return UnsentMessageView(
        outbox_id=row.id,
        author_type=AuthorType.AGENT if row.author_user_id else AuthorType.BOT,
        author_name=names.get(row.author_user_id) if row.author_user_id else None,
        message_type=row.message_type,
        content=_content(row),
        delivery_status="FAILED" if failed else "QUEUED",
        failure_reason=translate_send_failure(row.last_error) if failed else None,
        retryable=is_retryable(row),
        created_at=row.created_at,
    )


def _content(row: OutboxMessage) -> str:
    """Texto visible de la fila: el cuerpo, el pie del documento o su nombre de archivo."""

    payload = row.payload or {}
    return str(payload.get("body") or payload.get("caption") or payload.get("filename") or "")
