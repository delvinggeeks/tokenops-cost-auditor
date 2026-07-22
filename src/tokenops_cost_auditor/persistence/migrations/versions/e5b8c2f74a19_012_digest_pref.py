"""012 daily digest email preference (Wave B, 2026-07-22)

Additive: one nullable bool on users. None = on (the default), False = the
customer turned the daily spend digest off.

Revision ID: e5b8c2f74a19
Revises: d4a7b1e9c052
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b8c2f74a19"
down_revision: str | None = "d4a7b1e9c052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("daily_digest_emails", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "daily_digest_emails")
