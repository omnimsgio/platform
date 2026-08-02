"""WhatsApp provisioning metadata (P2.1) — rollback-safe nullable columns.

Revision ID: 006_wa_provisioning_meta
Revises: 005_wa_conn_lifecycle
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_wa_provisioning_meta"
down_revision: str | None = "005_wa_conn_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("phone_registered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("webhook_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column(
            "provisioning_lock_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column(
            "provisioning_step_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("provider_error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("provider_error_subcode", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("provider_trace_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_whatsapp_accounts", "provider_trace_id")
    op.drop_column("tenant_whatsapp_accounts", "provider_error_subcode")
    op.drop_column("tenant_whatsapp_accounts", "provider_error_code")
    op.drop_column("tenant_whatsapp_accounts", "provisioning_step_started_at")
    op.drop_column("tenant_whatsapp_accounts", "provisioning_lock_until")
    op.drop_column("tenant_whatsapp_accounts", "webhook_verified_at")
    op.drop_column("tenant_whatsapp_accounts", "phone_registered_at")
