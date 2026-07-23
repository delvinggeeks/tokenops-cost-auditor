"""015 benchmark sharing preference (R-F1 SIGN-OFF, founder 2026-07-23)

Additive: one nullable bool on users. None = included in cross-customer
peer benchmarks (the disclosed default); False = excluded. The signed-off
promise this pairs with: logs and prompts are never used to train any
model — only anonymized counts and fix outcomes enter the cohort, and this
flag removes an account from even that.

Revision ID: d7b28e41c6f9
Revises: c9e51a7d20b4
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7b28e41c6f9"
down_revision: str | None = "c9e51a7d20b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("benchmark_sharing", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "benchmark_sharing")
