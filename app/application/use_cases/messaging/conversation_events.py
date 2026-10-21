"""Armado de los eventos de la bandeja (spec 09, sección 8). Funciones puras.

``conversation.updated`` lleva aquí solo lo que el evento del gateway y el vínculo permiten
saber; los campos que exigen consultas por lote (``lead_status``, ``quote_status``,
``assigned_user_name``) los suma la bandeja de lectura (B5).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.application.dtos.conversation_event_dto import ConversationEvent, ConversationEventType
from app.application.dtos.gateway_event_dto import ConversationSnapshot, MessageDetails
from app.application.dtos.messaging_dto import (
    AuthorType,
    ConversationLifecycle,
    MessageAttachment,
    MessageDirection,
)
from app.application.use_cases.messaging.failure_catalog import translate_delivery_failure
from app.domain.entities.client import Client
from app.domain.entities.conversation_link import ConversationLink
from app.domain.entities.outbox_message import OutboxMessage
from app.domain.value_objects.outbox import DeliveryStatus, OutboxStatus

PREVIEW_MAX_CHARS = 120
ATTACHMENT_PREVIEW = "[Adjunto]"
SERVICE_WINDOW = timedelta(hours=24)
_UNREPORTED = "SENT"
_ATTACHMENT_PATH = "/api/v1/conversations/{conversation_id}/attachments/{attachment_id}"


def message_created_event(
    *,
    external_message_id: str,
    conversation_id: int,
    direction: MessageDirection,
    author_type: AuthorType | None,
    content: str,
    details: MessageDetails,
    at: datetime,
    outbox: OutboxMessage | None,
) -> ConversationEvent:
    """``message.created``: ``at`` es la hora del mensaje, o la de recepción si no la trae."""

    delivery = _delivery_status(direction, details, outbox)
    return ConversationEvent(
        event=ConversationEventType.MESSAGE_CREATED,
        data={
            "chatwoot_conversation_id": conversation_id,
            "message": {
                "id": _message_id(external_message_id),
                "direction": direction.value,
                "author_type": author_type.value if author_type is not None else None,
                "content": content,
                "attachments": [_attachment(conversation_id, a) for a in details.attachments],
                "created_at": _iso(at),
                **_delivery_fields(
                    delivery,
                    details.error or _outbox_error(outbox),
                    outbox,
                    unreported=_UNREPORTED if direction is MessageDirection.OUTGOING else None,
                ),
            },
        },
    )


def message_updated_event(
    *,
    external_message_id: str,
    conversation_id: int,
    status: DeliveryStatus,
    error: str | None,
    outbox: OutboxMessage | None,
) -> ConversationEvent:
    """``message.updated``: nuevo estado de entrega con el motivo ya traducido."""

    return ConversationEvent(
        event=ConversationEventType.MESSAGE_UPDATED,
        data={
            "chatwoot_conversation_id": conversation_id,
            "message": {
                "id": _message_id(external_message_id),
                **_delivery_fields(status, error, outbox),
            },
        },
    )


def conversation_updated_event(
    *,
    conversation_id: int,
    snapshot: ConversationSnapshot,
    link: ConversationLink,
    client: Client | None,
    content: str,
    details: MessageDetails,
    at: datetime,
) -> ConversationEvent:
    expires_at = (
        link.last_client_message_at + SERVICE_WINDOW if link.last_client_message_at else None
    )
    phone = snapshot.contact_phone.value if snapshot.contact_phone else None
    name = client.full_name if client else snapshot.contact_name or phone
    return ConversationEvent(
        event=ConversationEventType.CONVERSATION_UPDATED,
        data={
            "chatwoot_conversation_id": conversation_id,
            "client": {
                "id": str(client.id) if client else None,
                "name": name,
                "phone": phone,
            },
            "quote_id": str(link.quote_id) if link.quote_id else None,
            "status": snapshot.lifecycle.value.lower(),
            "mode": "HUMAN" if snapshot.lifecycle is ConversationLifecycle.OPEN else "BOT",
            "assigned_user_id": str(link.assigned_user_id) if link.assigned_user_id else None,
            "unread_count": snapshot.unread_count,
            "handoff_reason": link.handoff_reason.value if link.handoff_reason else None,
            "handed_off_at": _iso(link.handed_off_at) if link.handed_off_at else None,
            "last_message_preview": _preview(content, bool(details.attachments)),
            "last_message_at": _iso(at),
            "service_window_open": snapshot.can_reply,
            "service_window_expires_at": _iso(expires_at) if expires_at else None,
        },
    )


def _delivery_status(
    direction: MessageDirection, details: MessageDetails, outbox: OutboxMessage | None
) -> DeliveryStatus | None:
    """Los entrantes no tienen estado de entrega."""

    if direction is not MessageDirection.OUTGOING:
        return None
    return details.delivery_status or (outbox.delivery_status if outbox else None)


def _delivery_fields(
    status: DeliveryStatus | None,
    error: str | None,
    outbox: OutboxMessage | None,
    *,
    unreported: str | None = None,
) -> dict[str, Any]:
    """``unreported`` es el estado que se informa mientras Chatwoot no avise otro."""

    failure = translate_delivery_failure(error) if status is DeliveryStatus.FAILED else None
    return {
        "delivery_status": status.value if status else unreported,
        "failure_reason": failure.reason if failure else None,
        "failure_code": failure.code if failure else None,
        "outbox_id": str(outbox.id) if outbox else None,
        "retryable": _retryable(outbox),
    }


def _retryable(outbox: OutboxMessage | None) -> bool:
    if outbox is None or outbox.payload is None:
        return False
    return outbox.status is OutboxStatus.FAILED or outbox.delivery_status is DeliveryStatus.FAILED


def _outbox_error(outbox: OutboxMessage | None) -> str | None:
    return outbox.delivery_error if outbox else None


def _message_id(external_message_id: str) -> int | str:
    return int(external_message_id) if external_message_id.isdecimal() else external_message_id


def _attachment(conversation_id: int, attachment: MessageAttachment) -> dict[str, Any]:
    return {
        "id": attachment.attachment_id,
        "file_type": attachment.file_type,
        "content_type": attachment.content_type,
        "url": _ATTACHMENT_PATH.format(
            conversation_id=conversation_id, attachment_id=attachment.attachment_id
        ),
    }


def _preview(content: str, has_attachments: bool) -> str | None:
    text = content.strip()
    if text:
        return text[:PREVIEW_MAX_CHARS]
    return ATTACHMENT_PREVIEW if has_attachments else None


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
