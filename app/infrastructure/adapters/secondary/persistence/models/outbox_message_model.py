"""Tabla outbox_messages (0001_initial_schema + seguimiento de entrega de 0004)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class OutboxMessageModel(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        CheckConstraint(
            "message_type IN ('TEXT', 'TEMPLATE', 'INTERACTIVE', 'DOCUMENT')",
            name="ck_outbox_messages_message_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')", name="ck_outbox_messages_status"
        ),
        CheckConstraint("attempts >= 0", name="ck_outbox_messages_attempts_non_negative"),
        CheckConstraint("max_attempts > 0", name="ck_outbox_messages_max_attempts_positive"),
        CheckConstraint(
            "delivery_status IN ('DELIVERED', 'READ', 'FAILED')",
            name="ck_outbox_messages_delivery_status",
        ),
        UniqueConstraint("external_message_id", name="uq_outbox_messages_external_message_id"),
        Index("ix_outbox_messages_next_attempt_at", "next_attempt_at"),
        Index("ix_outbox_messages_status_next_attempt", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # none_as_null: un payload anulado debe quedar en SQL NULL y no en el JSON ``null``.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'PENDING'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    external_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redact_after_send: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
