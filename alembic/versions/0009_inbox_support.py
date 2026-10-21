"""Soporte de la bandeja de conversaciones de E1 (spec 09, sección 5.1).

* ``conversation_links.client_id`` admite ``NULL``: el vínculo ya no crea clientes (D1).
* ``conversation_links``: ``last_client_message_at`` (D15) y la etapa «Evento realizado»
  (``event_done_at``, ``event_done_by_user_id``, ``lead_cycle_started_at``, D25).
* ``outbox_messages``: ``author_user_id`` (quién envió) y ``retried_external_message_id``
  (autoría conservada tras reintentar, D24).

El downgrade elimina los vínculos sin cliente, porque el esquema anterior no puede
representarlos.
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_inbox_support"
down_revision = "0008_contract_signature"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("conversation_links", "client_id", nullable=True)
    op.add_column(
        "conversation_links",
        sa.Column("last_client_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversation_links",
        sa.Column("event_done_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversation_links",
        sa.Column(
            "event_done_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_conversation_links_event_done_by_user_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "conversation_links",
        sa.Column("lead_cycle_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_conversation_links_event_done_by_user_id",
        "conversation_links",
        ["event_done_by_user_id"],
    )
    op.add_column(
        "outbox_messages",
        sa.Column(
            "author_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_outbox_messages_author_user_id"),
            nullable=True,
        ),
    )
    op.add_column(
        "outbox_messages", sa.Column("retried_external_message_id", sa.Text(), nullable=True)
    )
    op.create_index("ix_outbox_messages_author_user_id", "outbox_messages", ["author_user_id"])
    op.create_index(
        "ix_outbox_messages_retried_external_message_id",
        "outbox_messages",
        ["retried_external_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_retried_external_message_id", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_author_user_id", table_name="outbox_messages")
    op.drop_column("outbox_messages", "retried_external_message_id")
    op.drop_column("outbox_messages", "author_user_id")
    op.drop_index("ix_conversation_links_event_done_by_user_id", table_name="conversation_links")
    for column in (
        "lead_cycle_started_at",
        "event_done_by_user_id",
        "event_done_at",
        "last_client_message_at",
    ):
        op.drop_column("conversation_links", column)
    op.execute("DELETE FROM conversation_links WHERE client_id IS NULL")
    op.alter_column("conversation_links", "client_id", nullable=False)
