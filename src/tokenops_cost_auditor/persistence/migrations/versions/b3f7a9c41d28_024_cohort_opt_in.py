"""024 workspace cohort-export consent (T-F2 · FR-35)

Additive, one column: workspaces.cohort_opt_in, NOT NULL default false —
EXPLICIT opt-in (the opposite direction from users.benchmark_sharing's
R-F1 opt-out). Existing rows backfill to false: absence of consent IS
the safe default, so no workspace enters the cohort export by migration.

Revision ID: b3f7a9c41d28
Revises: e1a6c8d92f43
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3f7a9c41d28"
down_revision: str | None = "e1a6c8d92f43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("cohort_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "cohort_opt_in")
