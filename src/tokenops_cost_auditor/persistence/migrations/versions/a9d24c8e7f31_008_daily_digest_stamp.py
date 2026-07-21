"""008 daily digest stamp (R-DAILY-LOOP, founder-ratified 2026-07-22)

Additive only: one nullable stamp on users — when the customer's daily
spend digest last went out, so a repeated tick never double-sends.

Revision ID: a9d24c8e7f31
Revises: d3f8a1c7e604
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9d24c8e7f31"
down_revision: str | None = "d3f8a1c7e604"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("last_daily_digest_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "last_daily_digest_at")
