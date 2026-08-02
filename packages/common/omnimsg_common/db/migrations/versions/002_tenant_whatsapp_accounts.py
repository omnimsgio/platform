"""Add tenant_whatsapp_accounts for per-tenant Meta Cloud API config.

Revision ID: 002_tenant_whatsapp_accounts
Revises: 001_initial_schema
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_tenant_whatsapp_accounts"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_whatsapp_accounts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("business_access_token", sa.String(length=2048), nullable=False),
        sa.Column(
            "credit_line_attached",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "phone_number_id",
            name="uq_tenant_whatsapp_phone_number_id",
        ),
    )
    op.create_index(
        "ix_tenant_whatsapp_accounts_tenant_id",
        "tenant_whatsapp_accounts",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_whatsapp_accounts_tenant_id",
        table_name="tenant_whatsapp_accounts",
    )
    op.drop_table("tenant_whatsapp_accounts")
