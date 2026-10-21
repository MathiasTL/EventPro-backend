"""Persistir límites de solicitudes OTP entre procesos y reenvíos de enlace."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_contract_signature"
down_revision: str | None = "0007_contract_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("otp_last_requested_at", sa.DateTime(timezone=True)))
    op.add_column("contracts", sa.Column("otp_window_started_at", sa.DateTime(timezone=True)))
    op.add_column(
        "contracts",
        sa.Column("otp_request_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("contracts", "otp_request_count")
    op.drop_column("contracts", "otp_window_started_at")
    op.drop_column("contracts", "otp_last_requested_at")
