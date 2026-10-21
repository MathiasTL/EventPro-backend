"""DTOs de lectura de la bandeja de conversaciones (spec 09, secciones 4 y 7)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.application.dtos.messaging_dto import (
    AuthorType,
    ConversationLifecycle,
    ConversationStatus,
    MessageDirection,
)
from app.domain.entities.conversation_link import HandoffReason
from app.domain.entities.quote import QuoteStatus
from app.domain.value_objects.outbox import MessageType

# Tope de la bandeja en memoria (D12): 20 páginas de 25 de Chatwoot.
INBOX_SCAN_LIMIT = 500
SEARCH_MIN_CHARS = 2


class LeadStatus(StrEnum):
    """Estado comercial derivado de la cotización vinculada (4.2, D14); nunca se escribe."""

    QUOTING = "QUOTING"
    QUOTE_SENT = "QUOTE_SENT"
    PAYMENT_STARTED = "PAYMENT_STARTED"
    CONVERTED = "CONVERTED"
    QUOTE_CLOSED = "QUOTE_CLOSED"
    EVENT_DONE = "EVENT_DONE"


class AssignedFilter(StrEnum):
    ME = "me"
    UNASSIGNED = "unassigned"


@dataclass(frozen=True)
class ConversationFilters:
    """``assigned_user_id`` es la asignación efectiva pedida por un ``SUPERADMIN`` (4.1)."""

    mode: ConversationStatus | None = None
    assigned: AssignedFilter | None = None
    assigned_user_id: UUID | None = None
    q: str | None = None
    include_resolved: bool = False
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True)
class ConversationView:
    """Ítem de la bandeja (7.2). ``assigned_user_id`` ya es la asignación efectiva (4.1)."""

    chatwoot_conversation_id: int
    client_id: UUID | None
    client_name: str
    phone: str
    quote_id: UUID | None
    quote_status: QuoteStatus | None
    lead_status: LeadStatus
    lifecycle: ConversationLifecycle
    mode: ConversationStatus
    assigned_user_id: UUID | None
    assigned_user_name: str | None
    unread_count: int
    handoff_reason: HandoffReason | None
    handed_off_at: datetime | None
    last_message_preview: str | None
    last_message_at: datetime | None
    service_window_open: bool
    service_window_expires_at: datetime | None


@dataclass(frozen=True)
class ConversationPage:
    items: Sequence[ConversationView]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class MessageAttachmentView:
    attachment_id: int
    file_type: str
    content_type: str | None


@dataclass(frozen=True)
class MessageView:
    """Mensaje del hilo (7.3). ``delivery_status`` es ``None`` en entrantes y avisos."""

    id: int | str
    direction: MessageDirection
    author_type: AuthorType | None
    author_name: str | None
    content: str
    attachments: Sequence[MessageAttachmentView]
    delivery_status: str | None
    failure_reason: str | None
    failure_code: int | None
    outbox_id: UUID | None
    retryable: bool
    created_at: datetime


@dataclass(frozen=True)
class UnsentMessageView:
    """Fila del outbox que aún no existe en Chatwoot; ``delivery_status`` es QUEUED o FAILED."""

    outbox_id: UUID
    author_type: AuthorType
    author_name: str | None
    message_type: MessageType
    content: str
    delivery_status: str
    failure_reason: str | None
    retryable: bool
    created_at: datetime


@dataclass(frozen=True)
class MessagePage:
    """Del más reciente al más antiguo; ``unsent`` solo viaja en la primera página."""

    items: Sequence[MessageView]
    has_more: bool
    unsent: Sequence[UnsentMessageView] | None
