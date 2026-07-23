"""018 ingest keys (S-0, R-SDK-PLATFORM)

Revision ID: a3e59c7f24d1
Revises: f2a94b6d81c3
Create Date: 2026-07-23

Additive only: the ingest_keys table backing the paste-able DSN
(TOKENOPS_COST_AUDITOR_DSN). key_hash is nullable — revoke DELETES the
key material and keeps the row for audit attribution.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a3e59c7f24d1"
down_revision: str | None = "f2a94b6d81c3"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "ingest_keys",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingest_keys")
