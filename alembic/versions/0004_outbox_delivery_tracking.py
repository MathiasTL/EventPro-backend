"""Seguimiento de entrega del outbox: identificador de Chatwoot, estado de WhatsApp y 6 intentos.

Solo agrega columnas y cambia el valor por defecto de ``max_attempts`` de 5 a 6 (RNF-03.2:
cinco reintentos más el primer envío). Las filas existentes conservan su ``max_attempts``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_outbox_delivery_tracking"
down_revision = "0003_manual_booking_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox_messages", sa.Column("external_message_id", sa.String(64), nullable=True))
    op.add_column("outbox_messages", sa.Column("conversation_id", sa.BigInteger(), nullable=True))
    op.add_column("outbox_messages", sa.Column("delivery_status", sa.String(20), nullable=True))
    op.add_column("outbox_messages", sa.Column("delivery_error", sa.Text(), nullable=True))
    op.add_column(
        "outbox_messages", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "outbox_messages", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "outbox_messages",
        sa.Column("redact_after_send", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_unique_constraint(
        "uq_outbox_messages_external_message_id", "outbox_messages", ["external_message_id"]
    )
    op.create_check_constraint(
        "ck_outbox_messages_delivery_status",
        "outbox_messages",
        "delivery_status IN ('DELIVERED', 'READ', 'FAILED')",
    )
    op.alter_column("outbox_messages", "max_attempts", server_default=sa.text("6"))


def downgrade() -> None:
    op.alter_column("outbox_messages", "max_attempts", server_default=sa.text("5"))
    op.drop_constraint("ck_outbox_messages_delivery_status", "outbox_messages", type_="check")
    op.drop_constraint("uq_outbox_messages_external_message_id", "outbox_messages", type_="unique")
    for column in (
        "redact_after_send",
        "read_at",
        "delivered_at",
        "delivery_error",
        "delivery_status",
        "conversation_id",
        "external_message_id",
    ):
        op.drop_column("outbox_messages", column)
