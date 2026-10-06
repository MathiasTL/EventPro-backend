"""catalogo y elencos

Revision ID: 0002_catalog_and_crews
Revises: 0001_base_roles_users
Create Date: 2026-10-05

Crea las tablas del catálogo (paquetes, temáticas, extras, inventario y sus
relaciones) y los elencos (E3, Sprint 0). El motor de disponibilidad
(``inventory_reservations`` y ``crew_assignments``) depende de ``events`` y se
creará en la Ola 1.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_catalog_and_crews"
down_revision: str | None = "0001_base_roles_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SERVICE_CATEGORY = "service_category IN ('SHOW', 'DJ', 'DECORATION', 'TENTS')"
_INVENTORY_SERVICE_CATEGORY = "service_category IN ('DECORATION', 'TENTS')"


def upgrade() -> None:
    op.create_table(
        "packages",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
    )

    op.create_table(
        "package_themes",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "package_id", sa.Uuid(as_uuid=True), sa.ForeignKey("packages.id"), nullable=False
        ),
        sa.Column("theme_id", sa.Uuid(as_uuid=True), sa.ForeignKey("themes.id"), nullable=False),
        sa.UniqueConstraint("package_id", "theme_id", name="uq_package_themes"),
    )

    op.create_table(
        "extras",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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


def downgrade() -> None:
    op.drop_table("crews")
    op.drop_index(
        "ix_package_inventory_items_inventory_item_id",
        table_name="package_inventory_items",
    )
    op.drop_table("package_inventory_items")
    op.drop_table("inventory_items")
    op.drop_table("extras")
    op.drop_table("package_themes")
    op.drop_table("themes")
    op.drop_table("packages")
