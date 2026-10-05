"""base: roles y users

Revision ID: 0001_base_roles_users
Revises:
Create Date: 2026-10-05

Crea las tablas base de identidad (E2). Se necesitan antes de ``crews``, que tiene
una clave foránea a ``users.id``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_base_roles_users"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role_id", sa.Uuid(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(150), nullable=False, unique=True),
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


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("roles")
