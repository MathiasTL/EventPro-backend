"""pagos y comprobantes

Revision ID: 0003_payments
Revises: 0002_catalog_and_crews
Create Date: 2026-10-05

Crea la tabla ``payments`` (E5, Christian): adelantos (ADVANCE), cobros in situ
(BALANCE, EXTENSION), evidencia, verificación y auditoría. Las FK a ``quotes`` y
``events`` se añadirán cuando E1/E6 creen esas tablas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_payments"
down_revision: str | None = "0002_catalog_and_crews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONCEPTS = "concept IN ('ADVANCE', 'BALANCE', 'EXTENSION')"
_METHODS = "payment_method IN ('YAPE', 'PLIN', 'BANK_TRANSFER', 'CASH')"
_VALIDATION_STATUSES = (
    "validation_status IN ('PENDING_VERIFICATION', 'REQUIRES_MANUAL_APPROVAL', "
    "'VERIFIED', 'REJECTED', 'REFUND_PENDING', 'REFUNDED')"
)
_AUDIT_STATUSES = "audit_status IN ('UNREVIEWED', 'REVIEWED', 'FLAGGED')"


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("quote_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("concept", sa.String(20), nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("evidence_path", sa.String(255), nullable=False),
        sa.Column("transaction_reference", sa.String(60), nullable=True),
        sa.Column(
            "validation_status",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'PENDING_VERIFICATION'"),
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("audit_status", sa.String(20), nullable=True),
        sa.Column("audited_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("audited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["audited_by_user_id"], ["users.id"]),
        sa.Index("ix_payments_quote_id", "quote_id"),
        sa.Index("ix_payments_event_id", "event_id"),
        sa.CheckConstraint(_CONCEPTS, name="ck_payments_concept"),
        sa.CheckConstraint(_METHODS, name="ck_payments_payment_method"),
        sa.CheckConstraint(_VALIDATION_STATUSES, name="ck_payments_validation_status"),
        sa.CheckConstraint(_AUDIT_STATUSES, name="ck_payments_audit_status"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "(concept = 'ADVANCE') = (audit_status IS NULL)",
            name="ck_payments_concept_audit",
        ),
        sa.CheckConstraint(
            "concept = 'ADVANCE' OR (validation_status = 'VERIFIED' AND "
            "registered_by_user_id IS NOT NULL AND event_id IS NOT NULL)",
            name="ck_payments_in_situ_verified",
        ),
        sa.CheckConstraint(
            "audit_status IS DISTINCT FROM 'FLAGGED' OR audit_notes IS NOT NULL",
            name="ck_payments_flagged_requires_notes",
        ),
    )


def downgrade() -> None:
    op.drop_table("payments")
