"""Motivo de cancelación de la cotización (US-07, RN-09)."""

import sqlalchemy as sa

from alembic import op

revision = "0010_quote_cancellation_reason"
down_revision = "0009_inbox_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("cancellation_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("quotes", "cancellation_reason")
