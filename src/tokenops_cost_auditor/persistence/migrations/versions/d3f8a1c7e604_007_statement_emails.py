"""007 statement email preference (V-D7 settings)

Additive only: one nullable column on users. NULL means "not chosen yet",
which reads as opted IN — the statement is the product's core artifact.

Revision ID: d3f8a1c7e604
Revises: b7e41d92c8aa
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3f8a1c7e604"
down_revision: str | None = "b7e41d92c8aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("statement_emails", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "statement_emails")
