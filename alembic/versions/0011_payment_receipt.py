"""Comprobante por WhatsApp: método de pago UNSPECIFIED y motivo de derivación PAYMENT_RECEIPT."""

import sqlalchemy as sa

from alembic import op

revision = "0011_payment_receipt"
down_revision = "0010_quote_cancellation_reason"
branch_labels = None
depends_on = None

_PAYMENT_METHOD_CHECK = "ck_payments_payment_method"
_HANDOFF_REASON_CHECK = "ck_conversation_links_handoff_reason"
_METHODS = "'YAPE', 'PLIN', 'BANK_TRANSFER', 'CASH'"
_REASONS = "'CLIENT_REQUEST', 'BOT_NOT_UNDERSTOOD', 'MANUAL_TAKEOVER', 'BOT_ERROR'"


def _replace(table: str, name: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    _replace("payments", _PAYMENT_METHOD_CHECK, f"payment_method IN ({_METHODS}, 'UNSPECIFIED')")
    _replace(
        "conversation_links",
        _HANDOFF_REASON_CHECK,
        f"handoff_reason IN ({_REASONS}, 'PAYMENT_RECEIPT')",
    )


def downgrade() -> None:
    # Un pago sin medio confirmado no se puede reasignar sin inventar un dato financiero.
    pending = op.get_bind().execute(
        sa.text("SELECT 1 FROM payments WHERE payment_method = 'UNSPECIFIED' LIMIT 1")
    )
    if pending.first() is not None:
        raise RuntimeError(
            "Hay pagos con método UNSPECIFIED: confirma su método antes de revertir 0011."
        )
    # El motivo de derivación solo informa a la bandeja; el equivalente anterior es BOT_ERROR.
    op.execute(
        "UPDATE conversation_links SET handoff_reason = 'BOT_ERROR' "
        "WHERE handoff_reason = 'PAYMENT_RECEIPT'"
    )
    _replace("payments", _PAYMENT_METHOD_CHECK, f"payment_method IN ({_METHODS})")
    _replace("conversation_links", _HANDOFF_REASON_CHECK, f"handoff_reason IN ({_REASONS})")
