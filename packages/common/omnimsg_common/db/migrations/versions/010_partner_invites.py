"""Partner onboarding invites (capability-partner-onboarding-v1).

Revision ID: 010_partner_invites
Revises: 009_api_key_rotation
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010_partner_invites"
down_revision: str | None = "009_api_key_rotation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "partner_invites",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column("partner_name", sa.String(length=255), nullable=False),
        sa.Column("partner_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_actor", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("api_key_id", sa.String(length=64), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_partner_invites_tenant_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["api_keys.id"],
            name="fk_partner_invites_api_key_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_partner_invites_token_hash"),
    )
    op.create_index("ix_partner_invites_status", "partner_invites", ["status"])
    op.create_index("ix_partner_invites_expires_at", "partner_invites", ["expires_at"])
    op.create_index("ix_partner_invites_tenant_id", "partner_invites", ["tenant_id"])
    op.create_index("ix_partner_invites_api_key_id", "partner_invites", ["api_key_id"])


def downgrade() -> None:
    op.drop_index("ix_partner_invites_api_key_id", table_name="partner_invites")
    op.drop_index("ix_partner_invites_tenant_id", table_name="partner_invites")
    op.drop_index("ix_partner_invites_expires_at", table_name="partner_invites")
    op.drop_index("ix_partner_invites_status", table_name="partner_invites")
    op.drop_table("partner_invites")
