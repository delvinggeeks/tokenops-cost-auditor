"""006 audit equiv_spend + statement subject (V-D6)

Additive only: nullable columns on audits and statements.

Revision ID: b7e41d92c8aa
Revises: c92d7f31ab04
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e41d92c8aa"
down_revision: str | None = "c92d7f31ab04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audits", sa.Column("equiv_spend", sa.Boolean(), nullable=True))
    op.add_column("statements", sa.Column("subject", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("statements", "subject")
    op.drop_column("audits", "equiv_spend")
