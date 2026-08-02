"""WhatsApp inbound message thread fields (P3.1) — rollback-safe.

Revision ID: 007_message_inbound_thread
Revises: 006_wa_provisioning_meta
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_message_inbound_thread"
down_revision: str | None = "006_wa_provisioning_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "direction",
            sa.String(length=16),
            nullable=False,
            server_default="outbound",
        ),
    )
    op.add_column(
        "messages",
        sa.Column("from_address", sa.String(length=320), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column(
            "conversation_id",
            sa.String(length=64),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "messages",
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_messages_tenant_provider_message",
        "messages",
        ["tenant_id", "provider_message_id"],
        unique=True,
        postgresql_where=sa.text("provider_message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_messages_tenant_conversation_created",
        "messages",
        ["tenant_id", "conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_tenant_conversation_created", table_name="messages")
    op.drop_index("uq_messages_tenant_provider_message", table_name="messages")
    op.drop_column("messages", "provider_message_id")
    op.drop_column("messages", "conversation_id")
    op.drop_column("messages", "from_address")
    op.drop_column("messages", "direction")
