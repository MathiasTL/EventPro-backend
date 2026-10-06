"""payments base US-11/US-12

Revision ID: 0006_payments
Revises: 0005_event_actual_start_time
Create Date: 2026-10-06 18:00:00.000000

Crea la tabla payments de E5. quote_id queda sin FK hasta E1; event_id referencia
events. id de usuario referencia users.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_payments"
down_revision: str | None = "0005_event_actual_start_time"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("concept", sa.String(length=20), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("evidence_path", sa.String(length=255), nullable=False),
        sa.Column("transaction_reference", sa.String(length=60), nullable=True),
        sa.Column(
            "validation_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'PENDING_VERIFICATION'"),
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("audit_status", sa.String(length=20), nullable=True),
        sa.Column("audited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("audited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "concept IN ('ADVANCE', 'BALANCE', 'EXTENSION')", name="ck_payments_concept"
        ),
        sa.CheckConstraint(
            "payment_method IN ('YAPE', 'PLIN', 'BANK_TRANSFER', 'CASH')",
            name="ck_payments_payment_method",
        ),
        sa.CheckConstraint(
            "validation_status IN ('PENDING_VERIFICATION', 'REQUIRES_MANUAL_APPROVAL', "
            "'VERIFIED', 'REJECTED', 'REFUND_PENDING', 'REFUNDED')",
            name="ck_payments_validation_status",
        ),
        sa.CheckConstraint(
            "audit_status IN ('UNREVIEWED', 'REVIEWED', 'FLAGGED')",
            name="ck_payments_audit_status",
        ),
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
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["audited_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_quote_id"), "payments", ["quote_id"], unique=False)
    op.create_index(op.f("ix_payments_event_id"), "payments", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_event_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_quote_id"), table_name="payments")
    op.drop_table("payments")
