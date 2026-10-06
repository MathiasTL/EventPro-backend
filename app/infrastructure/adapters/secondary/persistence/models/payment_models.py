"""Modelo ORM de pagos (épica E5, Christian).

Esquema alineado a la tabla ``payments`` (diccionario 2.15). Las FK a ``quotes``
y ``events`` se añadirán cuando E1/E6 creen esas tablas (Sprint 0/Ola 1); por
ahora ``quote_id`` y ``event_id`` son UUID indexados sin constraint.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.adapters.secondary.persistence.models.base import Base

_CONCEPTS = "concept IN ('ADVANCE', 'BALANCE', 'EXTENSION')"
_METHODS = "payment_method IN ('YAPE', 'PLIN', 'BANK_TRANSFER', 'CASH')"
_VALIDATION_STATUSES = (
    "validation_status IN ('PENDING_VERIFICATION', 'REQUIRES_MANUAL_APPROVAL', "
    "'VERIFIED', 'REJECTED', 'REFUND_PENDING', 'REFUNDED')"
)
_AUDIT_STATUSES = "audit_status IN ('UNREVIEWED', 'REVIEWED', 'FLAGGED')"


class PaymentModel(Base):
    """Pago de una cotización o evento (tabla ``payments``)."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(_CONCEPTS, name="ck_payments_concept"),
        CheckConstraint(_METHODS, name="ck_payments_payment_method"),
        CheckConstraint(_VALIDATION_STATUSES, name="ck_payments_validation_status"),
        CheckConstraint(_AUDIT_STATUSES, name="ck_payments_audit_status"),
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
        Index("ix_payments_quote_id", "quote_id"),
        Index("ix_payments_event_id", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    concept: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    evidence_path: Mapped[str] = mapped_column(String(255), nullable=False)
    transaction_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    validation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'PENDING_VERIFICATION'")
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    audit_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    audited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    audited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
