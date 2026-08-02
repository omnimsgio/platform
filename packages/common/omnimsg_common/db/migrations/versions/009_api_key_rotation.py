"""API key rotation columns (ADR-0022 C2.2).

Revision ID: 009_api_key_rotation
Revises: 008_admin_audit_events
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_api_key_rotation"
down_revision: str | None = "008_admin_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("replaced_by_key_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("replaces_key_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("grace_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_api_keys_replaced_by_key_id",
        "api_keys",
        "api_keys",
        ["replaced_by_key_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_api_keys_replaces_key_id",
        "api_keys",
        "api_keys",
        ["replaces_key_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_api_keys_grace_expires_at",
        "api_keys",
        ["grace_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_grace_expires_at", table_name="api_keys")
    op.drop_constraint("fk_api_keys_replaces_key_id", "api_keys", type_="foreignkey")
    op.drop_constraint(
        "fk_api_keys_replaced_by_key_id", "api_keys", type_="foreignkey"
    )
    op.drop_column("api_keys", "grace_expires_at")
    op.drop_column("api_keys", "replaces_key_id")
    op.drop_column("api_keys", "replaced_by_key_id")
