"""Add Embedded Signup metadata and error fields on tenant_whatsapp_accounts.

Revision ID: 003_whatsapp_account_es_metadata
Revises: 002_tenant_whatsapp_accounts
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_whatsapp_account_es_metadata"
down_revision: str | None = "002_tenant_whatsapp_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("token_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("graph_api_version", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("token_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("meta_business_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("last_error", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("last_correlation_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_whatsapp_accounts", "last_correlation_id")
    op.drop_column("tenant_whatsapp_accounts", "last_error")
    op.drop_column("tenant_whatsapp_accounts", "meta_business_id")
    op.drop_column("tenant_whatsapp_accounts", "token_source")
    op.drop_column("tenant_whatsapp_accounts", "graph_api_version")
    op.drop_column("tenant_whatsapp_accounts", "token_expires_at")
    op.drop_column("tenant_whatsapp_accounts", "token_created_at")
