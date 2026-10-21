"""Observaciones del cliente en la cotización (US-03)."""

import sqlalchemy as sa

from alembic import op

revision = "0006_quote_observations"
down_revision = "0005_event_financial_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("observations", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("quotes", "observations")
