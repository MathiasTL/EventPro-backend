"""Correlativo y auditoría del ciclo de vida de contratos.

Revision ID: 0007_contract_management
Revises: 0006_quote_observations
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_contract_management"
down_revision: str | None = "0006_quote_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ACTIONS = (
    "OVERRIDE_MOBILITY",
    "OVERRIDE_TRANSIT_INTERVAL",
    "APPROVE_OVERBOOKED_PAYMENT",
    "REJECT_OVERBOOKED_PAYMENT",
    "AUDIT_PAYMENT",
    "MANUAL_CONTRACT",
    "CONTRACT_SIGNED",
    "SEND_CONVERSATION_MESSAGE",
    "OVERRIDE_CONVERSATION_ASSIGNMENT",
)
NEW_ACTIONS = ("CONTRACT_ISSUED", "CONTRACT_LINK_RESENT", "CONTRACT_REGENERATED", "CONTRACT_VOIDED")


def upgrade() -> None:
    op.drop_constraint("ck_contracts_pdf_path_required", "contracts", type_="check")
    op.create_check_constraint(
        "ck_contracts_pdf_path_required",
        "contracts",
        "status NOT IN ('ISSUED', 'SIGNED') OR pdf_storage_path IS NOT NULL",
    )
    op.execute("CREATE SEQUENCE contract_number_seq")
    # Evita reutilizar números de contratos emitidos antes de esta revisión.
    op.execute(
        "SELECT setval('contract_number_seq', GREATEST(1, COALESCE("
        "(SELECT max(substring(contract_number from 'CTR-[0-9]{4}-([0-9]+)$')::bigint) "
        "FROM contracts WHERE contract_number ~ '^CTR-[0-9]{4}-[0-9]+$'), 0) + 1), false)"
    )
    op.drop_constraint("ck_audit_logs_action", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_action", "audit_logs", f"action IN {OLD_ACTIONS + NEW_ACTIONS}"
    )


def downgrade() -> None:
    # No borrar ni reescribir la evidencia para forzar un downgrade en una base con uso real.
    used = op.get_bind().scalar(
        sa.text(f"SELECT count(*) FROM audit_logs WHERE action IN {NEW_ACTIONS}")
    )
    if used:
        raise RuntimeError("No se puede retirar la revisión con auditoría de contratos existente")
    missing = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM contracts WHERE status='VOIDED' AND pdf_storage_path IS NULL")
    )
    if missing:
        raise RuntimeError("El baseline no admite contratos anulados sin PDF")
    op.drop_constraint("ck_contracts_pdf_path_required", "contracts", type_="check")
    op.create_check_constraint(
        "ck_contracts_pdf_path_required",
        "contracts",
        "status = 'DRAFT' OR pdf_storage_path IS NOT NULL",
    )
    op.drop_constraint("ck_audit_logs_action", "audit_logs", type_="check")
    op.create_check_constraint("ck_audit_logs_action", "audit_logs", f"action IN {OLD_ACTIONS}")
    op.execute("DROP SEQUENCE contract_number_seq")
