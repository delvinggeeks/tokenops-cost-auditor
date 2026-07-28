"""024 workspace cohort opt-in (FR-35, R-MODEL-FACTORY, founder 2026-07-28)

Additive: one NOT NULL bool on workspaces, default False. Explicit opt-in to
the cohort export — the ONLY data path into the model factory. Absence =
excluded, the safe default IS the law; no backfill needed.

Revision ID: f7a2c8e93d15
Revises: e1a6c8d92f43
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f7a2c8e93d15"
down_revision: str | None = "e1a6c8d92f43"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("cohort_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "cohort_opt_in")
