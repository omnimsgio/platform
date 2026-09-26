"""Store Meta credit allocation config id per WhatsApp account.

Revision ID: 011_credit_allocation_config
Revises: 010_partner_invites
Create Date: 2026-09-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_credit_allocation_config"
down_revision: str | None = "010_partner_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_whatsapp_accounts",
        sa.Column("credit_allocation_config_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_whatsapp_accounts", "credit_allocation_config_id")
