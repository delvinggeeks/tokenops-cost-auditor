"""009 one comp credit per user (readiness audit 2026-07-22, Wave 1)

Partial unique index so a concurrent first-login can't double-grant the
free-audit meter. Dedupe first (keep a consumed credit if any, else the
earliest) so the index can be created on existing data. Additive.

Revision ID: b1e5f2c93a70
Revises: a9d24c8e7f31
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1e5f2c93a70"
down_revision: str | None = "a9d24c8e7f31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop any duplicate comp credits before enforcing uniqueness: keep the
    # consumed one (audit_id set) when present, else the lowest id.
    op.execute(
        sa.text(
            """
            DELETE FROM payments
            WHERE provider = 'comp' AND id NOT IN (
                SELECT keep_id FROM (
                    SELECT user_id,
                           COALESCE(
                               MIN(CASE WHEN audit_id IS NOT NULL THEN id END),
                               MIN(id)
                           ) AS keep_id
                    FROM payments WHERE provider = 'comp' GROUP BY user_id
                ) AS keeps
            )
            """
        )
    )
    op.create_index(
        "uq_payments_one_comp_per_user",
        "payments",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("provider = 'comp'"),
        postgresql_where=sa.text("provider = 'comp'"),
    )


def downgrade() -> None:
    op.drop_index("uq_payments_one_comp_per_user", table_name="payments")
