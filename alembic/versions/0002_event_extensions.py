"""US-18: extensiones cobradas y minutos acumulados.

Revision ID: 0002_event_extensions
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_event_extensions"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "legacy_extra_hours_amount",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_events_legacy_extra_nonnegative", "events", "legacy_extra_hours_amount >= 0"
    )
    op.execute(
        "UPDATE events SET legacy_extra_hours_amount = extra_hours_amount "
        "WHERE NOT EXISTS (SELECT 1 FROM payments WHERE payments.event_id = events.id "
        "AND payments.concept = 'EXTENSION')"
    )
    op.add_column(
        "events",
        sa.Column("extra_minutes_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "ck_events_extra_minutes_nonnegative", "events", "extra_minutes_total >= 0"
    )
    op.create_table(
        "event_extensions",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("extra_minutes", sa.Integer(), nullable=False),
        sa.Column("agreed_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.UniqueConstraint("payment_id"),
        sa.CheckConstraint("extra_minutes > 0", name="ck_event_extensions_minutes_positive"),
        sa.CheckConstraint("agreed_rate > 0", name="ck_event_extensions_rate_positive"),
    )
    op.create_index("ix_event_extensions_event_id", "event_extensions", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_event_extensions_event_id", table_name="event_extensions")
    op.drop_table("event_extensions")
    op.drop_constraint("ck_events_extra_minutes_nonnegative", "events", type_="check")
    op.drop_column("events", "extra_minutes_total")
    op.drop_constraint("ck_events_legacy_extra_nonnegative", "events", type_="check")
    op.drop_column("events", "legacy_extra_hours_amount")
