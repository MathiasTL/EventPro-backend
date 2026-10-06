"""events base US-16

Revision ID: 0004_events
Revises: 0003_auth_audit_tables
Create Date: 2026-10-06 10:39:46.173214

Generada con autogenerate sobre PostgreSQL 16 y revisada contra el diccionario.
quote_id conserva NOT NULL y UNIQUE, sin FK hasta que E1 integre quotes.
Esta revisión solo crea events; payments y crew_assignments pertenecen a E5/E3.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_events"
down_revision: str | None = "0003_auth_audit_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_code", sa.String(length=30), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("district", sa.String(length=80), nullable=False),
        sa.Column("client_observations", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'AWAITING_SIGNATURE'"),
            nullable=False,
        ),
        sa.Column("total_services_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_mobility_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("final_total_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "advance_paid",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "pre_show_balance_paid",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "extra_hours_amount",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('AWAITING_SIGNATURE', 'SCHEDULED', 'AWAITING_BALANCE', "
            "'IN_PROGRESS', 'EXTENDED', 'SETTLED', 'CANCELLED')",
            name="ck_events_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_code"),
        sa.UniqueConstraint("quote_id"),
    )
    op.create_index(op.f("ix_events_district"), "events", ["district"], unique=False)
    op.create_index(op.f("ix_events_event_date"), "events", ["event_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_events_event_date"), table_name="events")
    op.drop_index(op.f("ix_events_district"), table_name="events")
    op.drop_table("events")
