"""Admin audit events table (ADR-0022).

Revision ID: 008_admin_audit_events
Revises: 007_message_inbound_thread
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_admin_audit_events"
down_revision: str | None = "007_message_inbound_thread"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("request_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_admin_audit_events_created_at",
        "admin_audit_events",
        ["created_at"],
    )
    op.create_index(
        "ix_admin_audit_events_entity_type",
        "admin_audit_events",
        ["entity_type"],
    )
    op.create_index(
        "ix_admin_audit_events_entity_id",
        "admin_audit_events",
        ["entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_events_entity_id", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_entity_type", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_created_at", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
