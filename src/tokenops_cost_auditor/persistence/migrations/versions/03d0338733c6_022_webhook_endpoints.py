"""022 webhook endpoints (R-PLATFORM slice 3, S-5)

Revision ID: 03d0338733c6
Revises: d9f4e1a72b30
Create Date: 2026-07-27

Additive, two new tables (brand new — no backfill needed):
  * webhook_endpoints — a workspace-registered outbound delivery target.
    `secret` signs every outbound event (HMAC-SHA256); NULLed on revoke
    alongside `active=False` (authority law), row kept for delivery history.
  * webhook_deliveries — one row per best-effort delivery attempt (no durable
    retry queue this slice), so the UI can show recent status honestly.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "03d0338733c6"
down_revision: str | None = "d9f4e1a72b30"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("workspace_id", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(80), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhook_endpoints_workspace_id", "webhook_endpoints", ["workspace_id"])
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "endpoint_id",
            sa.String(32),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_endpoint_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhook_endpoints_workspace_id", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
