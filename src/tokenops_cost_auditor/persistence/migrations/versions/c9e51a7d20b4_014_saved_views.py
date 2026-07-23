"""014 saved views (FR-32 C3, R-PROCEED 2026-07-23)

Additive: one table. A saved view is a named, whitelisted filter set for
/explore — bookmark metadata only (FR-22-trivial: filter keys, no usage
data, no text). Export remains HELD on the registered data-export trigger.

Revision ID: c9e51a7d20b4
Revises: a7d40c91b3e5
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e51a7d20b4"
down_revision: str | None = "a7d40c91b3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("params", sa.Text(), nullable=False),
        # NOT NULL, matching the non-Optional ORM annotation and the 001/003
        # created_at convention (cold-review C3 f.3). Safe to edit in place:
        # 014 has never been applied outside rehearsal databases.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_saved_view_user_name"),
    )
    op.create_index("ix_saved_views_user_id", "saved_views", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_views_user_id", table_name="saved_views")
    op.drop_table("saved_views")
