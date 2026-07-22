"""010 session epoch (readiness audit 2026-07-22, Wave 3)

Additive: one nullable stamp on users. Any session cookie issued at-or-before
users.sessions_valid_from is rejected, so close-account / log-out-everywhere
can actually kill stateless signed-cookie sessions.

Revision ID: c2f6a4d18b93
Revises: b1e5f2c93a70
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2f6a4d18b93"
down_revision: str | None = "b1e5f2c93a70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("sessions_valid_from", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_valid_from")
