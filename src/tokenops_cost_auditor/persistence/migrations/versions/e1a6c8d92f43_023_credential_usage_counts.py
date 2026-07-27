"""023 credential usage counts (R-PLATFORM slice 5, Issue #59)

Revision ID: e1a6c8d92f43
Revises: 03d0338733c6
Create Date: 2026-07-27

Additive: one INTEGER NOT NULL DEFAULT 0 column on each credential table that
authenticates /api/v1 — `ingest_keys.request_count` and
`api_tokens.request_count` — alongside the existing `last_used_at`. Usage
VISIBILITY only (X-01/X-02 unchanged): never gates traffic, never enforced.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e1a6c8d92f43"
down_revision: str | None = "03d0338733c6"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "ingest_keys",
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "api_tokens",
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("api_tokens", "request_count")
    op.drop_column("ingest_keys", "request_count")
