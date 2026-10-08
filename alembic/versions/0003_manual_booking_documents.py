"""Documentos compartidos e idempotencia del proceso manual.

No publica archivos por PostgREST: conserva los permisos privados del backend.
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_manual_booking_documents"
down_revision = "0002_event_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("manual_request_hash", sa.String(64), nullable=True))
    op.create_index(
        "uq_quotes_manual_request_hash",
        "quotes",
        ["manual_request_hash"],
        unique=True,
        postgresql_where=sa.text("source='MANUAL' AND status IN ('PAYMENT_STARTED','CONVERTED')"),
    )
    op.create_table(
        "booking_documents",
        sa.Column("path", sa.String(255), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("octet_length(content) <= 5242880", name="ck_booking_document_size"),
    )
    op.execute("REVOKE ALL ON booking_documents FROM PUBLIC")
    # Los roles de Supabase no existen en PostgreSQL local/Testcontainers.
    op.execute("""
        DO $$ DECLARE role_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON booking_documents FROM %I', role_name);
          END IF;
        END LOOP; END $$;
    """)


def downgrade() -> None:
    op.drop_table("booking_documents")
    op.drop_index("uq_quotes_manual_request_hash", table_name="quotes")
    op.drop_column("quotes", "manual_request_hash")
