"""011 activity seen stamp (Wave B — activity center, 2026-07-22)

Additive: one nullable stamp on users — when the customer last opened their
activity feed, so the topbar bell can count what's new.

Revision ID: d4a7b1e9c052
Revises: c2f6a4d18b93
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4a7b1e9c052"
down_revision: str | None = "c2f6a4d18b93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("activity_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "activity_seen_at")
