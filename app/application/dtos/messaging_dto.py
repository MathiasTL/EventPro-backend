"""DTOs del puerto de mensajería (alineados con la especificación del gateway)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.value_objects.phone_number import PhoneNumber


class ConversationStatus(StrEnum):
    """Quién responde: el bot (``pending`` en Chatwoot) o un encargado (``open``)."""

    BOT = "BOT"
    HUMAN = "HUMAN"


class ConversationLifecycle(StrEnum):
    """Estado crudo de la conversación en Chatwoot (solo lectura; ver ``ConversationStatus``)."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class MessageDirection(StrEnum):
    """Sentido del mensaje; ``ACTIVITY`` es un aviso del sistema (reapertura, cambio de estado)."""

    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"
    ACTIVITY = "ACTIVITY"


class MessageSender(StrEnum):
    """Tipo de remitente que informa Chatwoot; no distingue al bot de un encargado (D3)."""

    CONTACT = "CONTACT"
    USER = "USER"
    AGENT_BOT = "AGENT_BOT"


@dataclass(frozen=True)
class MessageReceipt:
    message_id: str
    conversation_id: int
    sent_at: datetime


@dataclass(frozen=True)
class ListRow:
    id: str
    title: str
    description: str | None = None


@dataclass(frozen=True)
class ListSection:
    title: str
    rows: Sequence[ListRow]


@dataclass(frozen=True)
class ConversationSummary:
    """Fila de la bandeja; ``service_window_open`` es el ``can_reply`` de Chatwoot."""

    conversation_id: int
    phone: PhoneNumber
    status: ConversationStatus
    service_window_open: bool
    last_message_at: datetime | None
    lifecycle: ConversationLifecycle = ConversationLifecycle.PENDING
    contact_name: str | None = None
    unread_count: int = 0
    last_message_preview: str | None = None
    assignee_name: str | None = None


@dataclass(frozen=True)
class MessageAttachment:
    """Metadatos de un adjunto; la URL de Chatwoot nunca sale del adaptador."""

    attachment_id: int
    file_type: str
    content_type: str | None = None
    extension: str | None = None
    file_size: int | None = None
    filename: str | None = None


@dataclass(frozen=True)
class AttachmentContent:
    data: bytes
    content_type: str
    filename: str


@dataclass(frozen=True)
class ConversationMessage:
    message_id: str
    conversation_id: int
    direction: MessageDirection
    body: str | None
    sent_at: datetime
    attachment_filename: str | None = None
    sender: MessageSender | None = None
    sender_name: str | None = None
    status: str | None = None
    external_error: str | None = None
    content_type: str | None = None
    attachments: Sequence[MessageAttachment] = ()
