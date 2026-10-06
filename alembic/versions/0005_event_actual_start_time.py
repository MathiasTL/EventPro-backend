"""event actual start time

Revision ID: 0005_event_actual_start_time
Revises: 0004_events
Create Date: 2026-10-06 12:21:01.261203

Generada con autogenerate sobre PostgreSQL 16 y revisada manualmente.
La hora real es nullable y sin default: no se inventan horas de eventos históricos.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_event_actual_start_time"
down_revision: str | None = "0004_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events", sa.Column("actual_start_time", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("events", "actual_start_time")
