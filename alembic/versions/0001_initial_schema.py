"""initial schema: full documented data model

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-07

Baseline that consolidates the former revisions 0001-0006 and adds the tables that
were still missing (clients, quotes, quote_extras, inventory_reservations, contracts,
crew_assignments, outbox_messages and conversation_links). It follows
Docs/03-datos/02-diccionario-de-datos.md. ``event_extensions`` is intentionally not
part of this baseline: it ships as the next revision, chained from this one.

Design fixes applied on top of the former chain:
* ``events.quote_id`` and ``payments.quote_id`` reference ``quotes.id``.
* ``users.email`` is unique case-insensitively (unique index on ``lower(email)``).
* Every foreign key column is covered by an index.
* ``events`` money columns are non-negative and the time window is never empty.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SERVICE_CATEGORY = "service_category IN ('SHOW', 'DJ', 'DECORATION', 'TENTS')"
_INVENTORY_SERVICE_CATEGORY = "service_category IN ('DECORATION', 'TENTS')"

AUDIT_ACTIONS = (
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

EVENT_MONEY_COLUMNS = (
    "total_services_amount",
    "total_mobility_amount",
    "final_total_amount",
    "advance_paid",
    "pre_show_balance_paid",
    "extra_hours_amount",
)

# Creation order respects foreign key dependencies; downgrade drops in reverse.
TABLES_IN_CREATION_ORDER = (
    "roles",
    "users",
    "refresh_tokens",
    "audit_logs",
    "clients",
    "packages",
    "themes",
    "package_themes",
    "extras",
    "inventory_items",
    "package_inventory_items",
    "crews",
    "quotes",
    "quote_extras",
    "events",
    "payments",
    "contracts",
    "crew_assignments",
    "inventory_reservations",
    "outbox_messages",
    "conversation_links",
)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        sa.Uuid(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    _create_identity_tables()
    _create_catalog_tables()
    _create_commercial_tables()
    _create_operation_tables()
    _create_messaging_tables()


def _create_identity_tables() -> None:
    op.create_table(
        "roles",
        _uuid_pk(),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("role_id", sa.Uuid(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(150), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Case-insensitive uniqueness: "A@x.pe" and "a@x.pe" are the same login.
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_index("ix_users_role_id", "users", ["role_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_name", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("old_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"action IN {AUDIT_ACTIONS}",
            name="ck_audit_logs_action",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_name", "entity_id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])


def _create_catalog_tables() -> None:
    op.create_table(
        "packages",
        _uuid_pk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("service_category", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("direct_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.CheckConstraint(_SERVICE_CATEGORY, name="ck_packages_service_category"),
        sa.CheckConstraint("base_price > 0", name="ck_packages_base_price_positive"),
        sa.CheckConstraint("direct_cost >= 0", name="ck_packages_direct_cost_non_negative"),
        sa.CheckConstraint("duration_minutes > 0", name="ck_packages_duration_positive"),
    )

    op.create_table(
        "themes",
        _uuid_pk(),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
    )

    op.create_table(
        "package_themes",
        _uuid_pk(),
        sa.Column(
            "package_id", sa.Uuid(as_uuid=True), sa.ForeignKey("packages.id"), nullable=False
        ),
        sa.Column("theme_id", sa.Uuid(as_uuid=True), sa.ForeignKey("themes.id"), nullable=False),
        sa.UniqueConstraint("package_id", "theme_id", name="uq_package_themes"),
    )
    op.create_index("ix_package_themes_theme_id", "package_themes", ["theme_id"])

    op.create_table(
        "extras",
        _uuid_pk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sale_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("direct_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.CheckConstraint("sale_price >= 0", name="ck_extras_sale_price_non_negative"),
        sa.CheckConstraint("direct_cost >= 0", name="ck_extras_direct_cost_non_negative"),
    )

    op.create_table(
        "inventory_items",
        _uuid_pk(),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("service_category", sa.String(30), nullable=False),
        sa.Column("total_stock", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.CheckConstraint(_INVENTORY_SERVICE_CATEGORY, name="ck_inventory_items_service_category"),
        sa.CheckConstraint("total_stock >= 0", name="ck_inventory_items_total_stock_non_negative"),
    )

    op.create_table(
        "package_inventory_items",
        _uuid_pk(),
        sa.Column(
            "package_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inventory_item_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("inventory_items.id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("package_id", "inventory_item_id", name="uq_package_inventory_items"),
        sa.CheckConstraint("quantity > 0", name="ck_package_inventory_items_quantity_positive"),
    )
    op.create_index(
        "ix_package_inventory_items_inventory_item_id",
        "package_inventory_items",
        ["inventory_item_id"],
    )

    op.create_table(
        "crews",
        _uuid_pk(),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            unique=True,
            nullable=True,
        ),
        sa.Column("leader_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("service_category", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.CheckConstraint(_SERVICE_CATEGORY, name="ck_crews_service_category"),
    )


def _create_commercial_tables() -> None:
    op.create_table(
        "clients",
        _uuid_pk(),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("dni", sa.String(8), nullable=True),
        sa.Column("ruc", sa.String(11), nullable=True),
        _created_at(),
        sa.CheckConstraint("dni ~ '^[0-9]+$' AND length(dni) = 8", name="ck_clients_dni_format"),
        sa.CheckConstraint("ruc ~ '^[0-9]+$' AND length(ruc) = 11", name="ck_clients_ruc_format"),
    )

    op.create_table(
        "quotes",
        _uuid_pk(),
        sa.Column("client_id", sa.Uuid(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'WHATSAPP'")),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=False),
        sa.Column("location_address", sa.String(255), nullable=False),
        sa.Column("location_district", sa.String(80), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column(
            "package_id", sa.Uuid(as_uuid=True), sa.ForeignKey("packages.id"), nullable=False
        ),
        sa.Column("theme_id", sa.Uuid(as_uuid=True), sa.ForeignKey("themes.id"), nullable=True),
        sa.Column(
            "client_provides_mobility",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "calculated_distance_km",
            sa.Numeric(6, 2),
            nullable=True,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "calculated_transit_minutes",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "base_mobility_amount",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "final_mobility_amount",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
        sa.Column(
            "mobility_overridden", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")
        ),
        sa.Column("mobility_override_reason", sa.Text(), nullable=True),
        sa.Column("services_subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("advance_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("pending_balance", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'SENT'")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.CheckConstraint("source IN ('WHATSAPP', 'MANUAL')", name="ck_quotes_source"),
        sa.CheckConstraint(
            "status IN ('SENT', 'PAYMENT_STARTED', 'CONVERTED', 'EXPIRED', 'CANCELLED')",
            name="ck_quotes_status",
        ),
    )
    op.create_index("ix_quotes_client_id", "quotes", ["client_id"])
    op.create_index("ix_quotes_event_date", "quotes", ["event_date"])
    op.create_index("ix_quotes_location_district", "quotes", ["location_district"])
    op.create_index("ix_quotes_expires_at", "quotes", ["expires_at"])
    op.create_index("ix_quotes_package_id", "quotes", ["package_id"])
    op.create_index("ix_quotes_theme_id", "quotes", ["theme_id"])

    op.create_table(
        "quote_extras",
        _uuid_pk(),
        sa.Column(
            "quote_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("quotes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extra_id", sa.Uuid(as_uuid=True), sa.ForeignKey("extras.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_quote_extras_quantity_positive"),
    )
    op.create_index("ix_quote_extras_quote_id", "quote_extras", ["quote_id"])
    op.create_index("ix_quote_extras_extra_id", "quote_extras", ["extra_id"])


def _create_operation_tables() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_code", sa.String(length=30), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("district", sa.String(length=80), nullable=False),
        sa.Column("client_observations", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'AWAITING_SIGNATURE'"),
            nullable=False,
        ),
        sa.Column("total_services_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_mobility_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("final_total_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "advance_paid",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "pre_show_balance_paid",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "extra_hours_amount",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("actual_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('AWAITING_SIGNATURE', 'SCHEDULED', 'AWAITING_BALANCE', "
            "'IN_PROGRESS', 'EXTENDED', 'SETTLED', 'CANCELLED')",
            name="ck_events_status",
        ),
        *(
            sa.CheckConstraint(f"{column} >= 0", name=f"ck_events_{column}_non_negative")
            for column in EVENT_MONEY_COLUMNS
        ),
        # Events may cross midnight (the domain moves an earlier end to the next day),
        # so only an empty window is rejected; ``end_time > start_time`` would be wrong.
        sa.CheckConstraint("end_time <> start_time", name="ck_events_time_window_non_empty"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_code"),
        sa.UniqueConstraint("quote_id"),
    )
    op.create_index(op.f("ix_events_district"), "events", ["district"], unique=False)
    op.create_index(op.f("ix_events_event_date"), "events", ["event_date"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("concept", sa.String(length=20), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("evidence_path", sa.String(length=255), nullable=False),
        sa.Column("transaction_reference", sa.String(length=60), nullable=True),
        sa.Column(
            "validation_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'PENDING_VERIFICATION'"),
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("audit_status", sa.String(length=20), nullable=True),
        sa.Column("audited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("audited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "concept IN ('ADVANCE', 'BALANCE', 'EXTENSION')", name="ck_payments_concept"
        ),
        sa.CheckConstraint(
            "payment_method IN ('YAPE', 'PLIN', 'BANK_TRANSFER', 'CASH')",
            name="ck_payments_payment_method",
        ),
        sa.CheckConstraint(
            "validation_status IN ('PENDING_VERIFICATION', 'REQUIRES_MANUAL_APPROVAL', "
            "'VERIFIED', 'REJECTED', 'REFUND_PENDING', 'REFUNDED')",
            name="ck_payments_validation_status",
        ),
        sa.CheckConstraint(
            "audit_status IN ('UNREVIEWED', 'REVIEWED', 'FLAGGED')",
            name="ck_payments_audit_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "(concept = 'ADVANCE') = (audit_status IS NULL)",
            name="ck_payments_concept_audit",
        ),
        sa.CheckConstraint(
            "concept = 'ADVANCE' OR (validation_status = 'VERIFIED' AND "
            "registered_by_user_id IS NOT NULL AND event_id IS NOT NULL)",
            name="ck_payments_in_situ_verified",
        ),
        sa.CheckConstraint(
            "audit_status IS DISTINCT FROM 'FLAGGED' OR audit_notes IS NOT NULL",
            name="ck_payments_flagged_requires_notes",
        ),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["audited_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_quote_id"), "payments", ["quote_id"], unique=False)
    op.create_index(op.f("ix_payments_event_id"), "payments", ["event_id"], unique=False)
    op.create_index("ix_payments_verified_by_user_id", "payments", ["verified_by_user_id"])
    op.create_index("ix_payments_registered_by_user_id", "payments", ["registered_by_user_id"])
    op.create_index("ix_payments_audited_by_user_id", "payments", ["audited_by_user_id"])

    op.create_table(
        "contracts",
        _uuid_pk(),
        sa.Column("contract_number", sa.String(30), nullable=False, unique=True),
        sa.Column("event_id", sa.Uuid(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("pdf_storage_path", sa.String(255), nullable=True),
        sa.Column("signature_token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("signature_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_hash", sa.String(255), nullable=True),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("signature_image_path", sa.String(255), nullable=True),
        sa.Column("signer_ip", sa.String(45), nullable=True),
        sa.Column("signer_user_agent", sa.String(255), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sealed_pdf_storage_path", sa.String(255), nullable=True),
        sa.Column("sealed_pdf_sha256", sa.CHAR(64), nullable=True),
        sa.Column("is_timestamped", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("is_manual_mode", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("custom_clauses", sa.Text(), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'SIGNED', 'VOIDED')", name="ck_contracts_status"
        ),
        sa.CheckConstraint("otp_attempts >= 0", name="ck_contracts_otp_attempts_non_negative"),
        sa.CheckConstraint(
            "status = 'DRAFT' OR pdf_storage_path IS NOT NULL",
            name="ck_contracts_pdf_path_required",
        ),
        sa.CheckConstraint(
            "status <> 'SIGNED' OR (signed_at IS NOT NULL AND "
            "sealed_pdf_storage_path IS NOT NULL AND sealed_pdf_sha256 IS NOT NULL)",
            name="ck_contracts_signed_requires_seal",
        ),
    )
    op.create_index("ix_contracts_event_id", "contracts", ["event_id"])
    op.create_index(
        "uq_contracts_event_active",
        "contracts",
        ["event_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'VOIDED'"),
    )

    op.create_table(
        "crew_assignments",
        _uuid_pk(),
        sa.Column("event_id", sa.Uuid(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("crew_id", sa.Uuid(as_uuid=True), sa.ForeignKey("crews.id"), nullable=False),
        sa.Column("transit_interval_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "transit_interval_overridden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("event_id", "crew_id", name="uq_crew_assignments_event_crew"),
        sa.CheckConstraint(
            "transit_interval_minutes >= 0",
            name="ck_crew_assignments_transit_interval_non_negative",
        ),
    )
    # event_id is already covered by the leftmost column of uq_crew_assignments_event_crew.
    op.create_index("ix_crew_assignments_crew_id", "crew_assignments", ["crew_id"])

    op.create_table(
        "inventory_reservations",
        _uuid_pk(),
        sa.Column("event_id", sa.Uuid(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column(
            "inventory_item_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("inventory_items.id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'ACTIVE'")),
        _created_at(),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity_positive"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_inventory_reservations_window"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RELEASED')", name="ck_inventory_reservations_status"
        ),
    )
    op.create_index("ix_inventory_reservations_event_id", "inventory_reservations", ["event_id"])
    # Also covers the inventory_item_id foreign key (leftmost column).
    op.create_index(
        "ix_inventory_reservations_item_window",
        "inventory_reservations",
        ["inventory_item_id", "starts_at", "ends_at"],
    )


def _create_messaging_tables() -> None:
    op.create_table(
        "outbox_messages",
        _uuid_pk(),
        sa.Column("recipient_phone", sa.String(20), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "message_type IN ('TEXT', 'TEMPLATE', 'INTERACTIVE', 'DOCUMENT')",
            name="ck_outbox_messages_message_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')", name="ck_outbox_messages_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_messages_attempts_non_negative"),
        sa.CheckConstraint("max_attempts > 0", name="ck_outbox_messages_max_attempts_positive"),
    )
    op.create_index("ix_outbox_messages_next_attempt_at", "outbox_messages", ["next_attempt_at"])
    op.create_index(
        "ix_outbox_messages_status_next_attempt", "outbox_messages", ["status", "next_attempt_at"]
    )

    op.create_table(
        "conversation_links",
        _uuid_pk(),
        sa.Column("chatwoot_conversation_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("client_id", sa.Uuid(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("quote_id", sa.Uuid(as_uuid=True), sa.ForeignKey("quotes.id"), nullable=True),
        sa.Column(
            "assigned_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("handoff_reason", sa.String(30), nullable=True),
        sa.Column("handoff_summary", sa.Text(), nullable=True),
        sa.Column("handed_off_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "handoff_reason IN ('CLIENT_REQUEST', 'BOT_NOT_UNDERSTOOD', 'MANUAL_TAKEOVER', "
            "'BOT_ERROR')",
            name="ck_conversation_links_handoff_reason",
        ),
    )
    op.create_index("ix_conversation_links_client_id", "conversation_links", ["client_id"])
    op.create_index("ix_conversation_links_quote_id", "conversation_links", ["quote_id"])
    op.create_index(
        "ix_conversation_links_assigned_user",
        "conversation_links",
        ["assigned_user_id"],
        postgresql_where=sa.text("assigned_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Dropping a table also drops its indexes and constraints.
    for table in reversed(TABLES_IN_CREATION_ORDER):
        op.drop_table(table)
