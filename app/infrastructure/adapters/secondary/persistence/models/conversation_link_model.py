"""Tabla conversation_links (0001_initial_schema + 0007_inbox_support)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class ConversationLinkModel(Base):
    __tablename__ = "conversation_links"
    __table_args__ = (
        CheckConstraint(
            "handoff_reason IN ('CLIENT_REQUEST', 'BOT_NOT_UNDERSTOOD', 'MANUAL_TAKEOVER', "
            "'BOT_ERROR')",
            name="ck_conversation_links_handoff_reason",
        ),
        Index("ix_conversation_links_client_id", "client_id"),
        Index("ix_conversation_links_quote_id", "quote_id"),
        Index(
            "ix_conversation_links_assigned_user",
            "assigned_user_id",
            postgresql_where=sql_text("assigned_user_id IS NOT NULL"),
        ),
        Index("ix_conversation_links_event_done_by_user_id", "event_done_by_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    chatwoot_conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    client_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id"), nullable=True
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("quotes.id"), nullable=True
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    handoff_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    handoff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    handed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_client_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    event_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_done_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    lead_cycle_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("CURRENT_TIMESTAMP")
    )
