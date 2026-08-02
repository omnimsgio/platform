"""WhatsApp connection lifecycle fields and status backfill.

Revision ID: 005_wa_conn_lifecycle
Revises: 004_conversations_and_referrals
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_wa_conn_lifecycle"
down_revision: str | None = "004_conversations_and_referrals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("status_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column(
            "lifecycle_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("recovery_target", sa.String(length=64), nullable=True),
    )

    op.alter_column(
        "tenant_whatsapp_accounts",
        "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
        server_default="EMBEDDED_SIGNUP_STARTED",
    )
    op.alter_column(
        "tenant_whatsapp_accounts",
        "waba_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.alter_column(
        "tenant_whatsapp_accounts",
        "phone_number_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.alter_column(
        "tenant_whatsapp_accounts",
        "business_access_token",
        existing_type=sa.String(length=2048),
        nullable=True,
    )

    op.execute(
        sa.text(
            """
            UPDATE tenant_whatsapp_accounts
            SET
              status_reason = CASE status
                WHEN 'active' THEN 'DEV_BOOTSTRAP'
                WHEN 'pending' THEN 'ES_STARTED'
                WHEN 'error' THEN 'ES_HEALTH_FAILED'
                ELSE status_reason
              END,
              status = CASE status
                WHEN 'active' THEN 'READY'
                WHEN 'pending' THEN 'EMBEDDED_SIGNUP_STARTED'
                WHEN 'error' THEN 'ERROR'
                ELSE status
              END,
              lifecycle_version = 1
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE tenant_whatsapp_accounts
            SET status = CASE status
                WHEN 'READY' THEN 'active'
                WHEN 'EMBEDDED_SIGNUP_STARTED' THEN 'pending'
                WHEN 'BUSINESS_CONNECTED' THEN 'pending'
                WHEN 'PHONE_PENDING' THEN 'pending'
                WHEN 'WEBHOOK_PENDING' THEN 'pending'
                WHEN 'HEALTH_CHECK_PENDING' THEN 'pending'
                WHEN 'ERROR' THEN 'error'
                WHEN 'DISCONNECTED' THEN 'error'
                ELSE status
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE tenant_whatsapp_accounts
            SET waba_id = COALESCE(waba_id, 'unknown'),
                phone_number_id = COALESCE(phone_number_id, id),
                business_access_token = COALESCE(
                    business_access_token, 'pending_exchange'
                )
            """
        )
    )
    op.alter_column(
        "tenant_whatsapp_accounts",
        "business_access_token",
        existing_type=sa.String(length=2048),
        nullable=False,
    )
    op.alter_column(
        "tenant_whatsapp_accounts",
        "phone_number_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "tenant_whatsapp_accounts",
        "waba_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "tenant_whatsapp_accounts",
        "status",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
        server_default="active",
    )
    op.drop_column("tenant_whatsapp_accounts", "recovery_target")
    op.drop_column("tenant_whatsapp_accounts", "lifecycle_version")
    op.drop_column("tenant_whatsapp_accounts", "status_reason")
