"""005 finding route (R-Q9 verified-savings correctness)

Additive only: one nullable column on findings.

Revision ID: c92d7f31ab04
Revises: f1c73b0a55e2
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c92d7f31ab04"
down_revision: str | None = "f1c73b0a55e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("route", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "route")
