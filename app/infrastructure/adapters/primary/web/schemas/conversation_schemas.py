"""Esquemas de la bandeja de conversaciones (spec 09, 7.2 y 7.3; REST 2.14)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.application.dtos.inbox_dto import (
    ConversationPage,
    ConversationView,
    LeadStatus,
    MessagePage,
    MessageView,
    UnsentMessageView,
)
from app.application.dtos.messaging_dto import AuthorType, ConversationStatus, MessageDirection
from app.domain.entities.conversation_link import HandoffReason
from app.domain.entities.quote import QuoteStatus
from app.domain.value_objects.outbox import MessageType


class ConversationClientResponse(BaseModel):
    id: UUID | None
    name: str
    phone: str


class ConversationResponse(BaseModel):
    chatwoot_conversation_id: int
    client: ConversationClientResponse
    quote_id: UUID | None
    quote_status: QuoteStatus | None
    lead_status: LeadStatus
    status: Literal["pending", "open", "resolved"]
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

    @classmethod
    def from_view(cls, view: ConversationView) -> "ConversationResponse":
        return cls(
            chatwoot_conversation_id=view.chatwoot_conversation_id,
            client=ConversationClientResponse(
                id=view.client_id, name=view.client_name, phone=view.phone
            ),
            quote_id=view.quote_id,
            quote_status=view.quote_status,
            lead_status=view.lead_status,
            status=view.lifecycle.value.lower(),  # type: ignore[arg-type]
            mode=view.mode,
            assigned_user_id=view.assigned_user_id,
            assigned_user_name=view.assigned_user_name,
            unread_count=view.unread_count,
            handoff_reason=view.handoff_reason,
            handed_off_at=view.handed_off_at,
            last_message_preview=view.last_message_preview,
            last_message_at=view.last_message_at,
            service_window_open=view.service_window_open,
            service_window_expires_at=view.service_window_expires_at,
        )


class ConversationPageResponse(BaseModel):
    items: list[ConversationResponse]
    page: int
    page_size: int
    total: int

    @classmethod
    def from_page(cls, page: ConversationPage) -> "ConversationPageResponse":
        return cls(
            items=[ConversationResponse.from_view(view) for view in page.items],
            page=page.page,
            page_size=page.page_size,
            total=page.total,
        )


class MessageAttachmentResponse(BaseModel):
    id: int
    file_type: str
    content_type: str | None
    url: str


class MessageResponse(BaseModel):
    id: int | str
    direction: MessageDirection
    author_type: AuthorType | None
    author_name: str | None
    content: str
    attachments: list[MessageAttachmentResponse]
    delivery_status: str | None
    failure_reason: str | None
    failure_code: int | None
    outbox_id: UUID | None
    retryable: bool
    created_at: datetime

    @classmethod
    def from_view(cls, conversation_id: int, view: MessageView) -> "MessageResponse":
        return cls(
            id=view.id,
            direction=view.direction,
            author_type=view.author_type,
            author_name=view.author_name,
            content=view.content,
            attachments=[
                MessageAttachmentResponse(
                    id=a.attachment_id,
                    file_type=a.file_type,
                    content_type=a.content_type,
                    # Ruta de EventPro; la URL de Chatwoot nunca sale del backend (D17).
                    url=f"/api/v1/conversations/{conversation_id}/attachments/{a.attachment_id}",
                )
                for a in view.attachments
            ],
            delivery_status=view.delivery_status,
            failure_reason=view.failure_reason,
            failure_code=view.failure_code,
            outbox_id=view.outbox_id,
            retryable=view.retryable,
            created_at=view.created_at,
        )


class UnsentMessageResponse(BaseModel):
    outbox_id: UUID
    author_type: AuthorType
    author_name: str | None
    message_type: MessageType
    content: str
    delivery_status: Literal["QUEUED", "FAILED"]
    failure_reason: str | None
    retryable: bool
    created_at: datetime

    @classmethod
    def from_view(cls, view: UnsentMessageView) -> "UnsentMessageResponse":
        return cls(
            outbox_id=view.outbox_id,
            author_type=view.author_type,
            author_name=view.author_name,
            message_type=view.message_type,
            content=view.content,
            delivery_status=view.delivery_status,  # type: ignore[arg-type]
            failure_reason=view.failure_reason,
            retryable=view.retryable,
            created_at=view.created_at,
        )


class MessagePageResponse(BaseModel):
    items: list[MessageResponse]
    has_more: bool
    # Solo en la primera página (sin ``before``); en las demás se omite del JSON.
    unsent: list[UnsentMessageResponse] | None = None

    @classmethod
    def from_page(cls, conversation_id: int, page: MessagePage) -> "MessagePageResponse":
        items = [MessageResponse.from_view(conversation_id, view) for view in page.items]
        if page.unsent is None:
            return cls(items=items, has_more=page.has_more)
        unsent = [UnsentMessageResponse.from_view(view) for view in page.unsent]
        return cls(items=items, has_more=page.has_more, unsent=unsent)
