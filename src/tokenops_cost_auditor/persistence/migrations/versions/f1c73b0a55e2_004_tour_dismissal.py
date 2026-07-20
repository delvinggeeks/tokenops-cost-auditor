"""004 tour dismissal + audit observed_days (PLAN-V15 V-D4g / R-Q9)

Additive only: nullable columns on users and audits.

Revision ID: f1c73b0a55e2
Revises: e4a91c55d201
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1c73b0a55e2"
down_revision: str | None = "e4a91c55d201"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("tour_dismissed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("audits", sa.Column("observed_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("audits", "observed_days")
    op.drop_column("users", "tour_dismissed_at")
