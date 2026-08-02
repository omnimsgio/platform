"""Add conversations and conversation_referrals for CTWA referral capture.

Revision ID: 004_conversations_and_referrals
Revises: 003_whatsapp_account_es_metadata
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_conversations_and_referrals"
down_revision: str | None = "003_whatsapp_account_es_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("contact_external_id", sa.String(length=128), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=True),
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
            "tenant_id",
            "channel",
            "contact_external_id",
            name="uq_conversations_tenant_channel_contact",
        ),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])

    op.create_table(
        "conversation_referrals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("headline", sa.String(length=512), nullable=True),
        sa.Column("body", sa.String(length=2048), nullable=True),
        sa.Column("media_type", sa.String(length=64), nullable=True),
        sa.Column("ctwa_clid", sa.String(length=512), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_message_id",
            name="uq_conversation_referrals_tenant_provider_message",
        ),
    )
    op.create_index(
        "ix_conversation_referrals_tenant_id",
        "conversation_referrals",
        ["tenant_id"],
    )
    op.create_index(
        "ix_conversation_referrals_conversation_id",
        "conversation_referrals",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_referrals_tenant_ctwa_clid",
        "conversation_referrals",
        ["tenant_id", "ctwa_clid"],
        postgresql_where=sa.text("ctwa_clid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_referrals_tenant_ctwa_clid",
        table_name="conversation_referrals",
    )
    op.drop_index(
        "ix_conversation_referrals_conversation_id",
        table_name="conversation_referrals",
    )
    op.drop_index(
        "ix_conversation_referrals_tenant_id",
        table_name="conversation_referrals",
    )
    op.drop_table("conversation_referrals")
    op.drop_index("ix_conversations_tenant_id", table_name="conversations")
    op.drop_table("conversations")
