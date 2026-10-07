"""Tabla payments de E5. quote_id referencia quotes en BD; el modelo de quotes llega con E1."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base


class PaymentModel(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_quote_id", "quote_id"),
        Index("ix_payments_event_id", "event_id"),
        CheckConstraint(
            "concept IN ('ADVANCE', 'BALANCE', 'EXTENSION')", name="ck_payments_concept"
        ),
        CheckConstraint(
            "payment_method IN ('YAPE', 'PLIN', 'BANK_TRANSFER', 'CASH')",
            name="ck_payments_payment_method",
        ),
        CheckConstraint(
            "validation_status IN ('PENDING_VERIFICATION', 'REQUIRES_MANUAL_APPROVAL', "
            "'VERIFIED', 'REJECTED', 'REFUND_PENDING', 'REFUNDED')",
            name="ck_payments_validation_status",
        ),
        CheckConstraint(
            "audit_status IN ('UNREVIEWED', 'REVIEWED', 'FLAGGED')",
            name="ck_payments_audit_status",
        ),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "(concept = 'ADVANCE') = (audit_status IS NULL)",
            name="ck_payments_concept_audit",
        ),
        CheckConstraint(
            "concept = 'ADVANCE' OR (validation_status = 'VERIFIED' AND "
            "registered_by_user_id IS NOT NULL AND event_id IS NOT NULL)",
            name="ck_payments_in_situ_verified",
        ),
        CheckConstraint(
            "audit_status IS DISTINCT FROM 'FLAGGED' OR audit_notes IS NOT NULL",
            name="ck_payments_flagged_requires_notes",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    quote_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    event_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("events.id"), nullable=True, index=True
    )
    concept: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    evidence_path: Mapped[str] = mapped_column(String(255), nullable=False)
    transaction_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    validation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'PENDING_VERIFICATION'")
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    audit_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    audited_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    audited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
