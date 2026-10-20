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


class MessageDirection(StrEnum):
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


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
    conversation_id: int
    phone: PhoneNumber
    status: ConversationStatus
    service_window_open: bool
    last_message_at: datetime | None


@dataclass(frozen=True)
class ConversationMessage:
    message_id: str
    conversation_id: int
    direction: MessageDirection
    body: str | None
    sent_at: datetime
    attachment_filename: str | None = None
