"""017 pipeline observability (WP-PIPELINE-UI)

Additive, three tables: stage_events (real per-stage timings + counts-only
detail incl. honest detector zeros), pull_events (every pull, failures
included — lineage, not just last_pull_at), alert_checks ("checked,
nothing crossed" recorded — silence you can verify).

Revision ID: f2a94b6d81c3
Revises: e8f31a5c92d7
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a94b6d81c3"
down_revision: str | None = "e8f31a5c92d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stage_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "audit_id",
            sa.String(32),
            sa.ForeignKey("audits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
    )
    op.create_index("ix_stage_events_audit_id", "stage_events", ["audit_id"])
    op.create_table(
        "pull_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_id",
            sa.String(32),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("buckets_in", sa.Integer(), nullable=False),
        sa.Column("upserted", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(300), nullable=True),
    )
    op.create_index("ix_pull_events_source_id", "pull_events", ["source_id"])
    op.create_table(
        "alert_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("rule", sa.String(32), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("crossed", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(200), nullable=False),
    )
    op.create_index("ix_alert_checks_user_id", "alert_checks", ["user_id"])


def downgrade() -> None:
    for name, table in (
        ("ix_alert_checks_user_id", "alert_checks"),
        ("ix_pull_events_source_id", "pull_events"),
        ("ix_stage_events_audit_id", "stage_events"),
    ):
        op.drop_index(name, table_name=table)
        op.drop_table(table)
