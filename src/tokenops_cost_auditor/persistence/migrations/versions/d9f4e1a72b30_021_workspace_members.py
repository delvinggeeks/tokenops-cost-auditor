"""021 workspace members (O-1b, R-ORG)

Revision ID: d9f4e1a72b30
Revises: c8e05a1f6b20
Create Date: 2026-07-24

Additive. The members half of O-1:
  * users.active_workspace_id — the server-side pointer to the workspace the
    user is currently acting in (backfilled to their personal workspace, so
    single-tenant behavior is unchanged). repo.active_workspace_id validates it
    against live memberships and falls back to the personal workspace, so a
    stale value can never leak — hence a plain String(32), no FK (the O-0
    additive-safe convention).
  * workspace_invites — invite by email with a one-shot HASHED code (the
    LinkCode grammar: code_hash unique, single-use via atomic consume).
  * workspace_id on alert_events / alert_checks — the OPERATIONAL owned-log
    tables O-0 left out; backfilled from each row's owner workspace so O-1b can
    scope their reads to the workspace (a member sees the workspace's alert
    history / silence ledger). PAYMENTS is deliberately NOT included: billing
    VISIBILITY is role-gated in O-2 (founder ruling 2026-07-24), so the payment
    ledger stays user-scoped until then and its workspace column lands with O-2.
    The audit ENGINE still never learns any of this (R-ORG).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d9f4e1a72b30"
down_revision: str | None = "c8e05a1f6b20"
branch_labels: None = None
depends_on: None = None

# operational owned-log tables that gain workspace_id in O-1b (keyed on user_id).
# payments is excluded on purpose — billing visibility is O-2 (role-gated).
LOG_TABLES: list[str] = ["alert_events", "alert_checks"]


def upgrade() -> None:
    # 1) the active-workspace pointer, backfilled to each user's personal workspace
    op.add_column("users", sa.Column("active_workspace_id", sa.String(32), nullable=True))

    # 2) invites — email + role + one-shot hashed code (LinkCode grammar)
    op.create_table(
        "workspace_invites",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "invited_by_user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consumed_by_user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 3) workspace_id on the three owned-log tables
    for table in LOG_TABLES:
        op.add_column(table, sa.Column("workspace_id", sa.String(32), nullable=True))
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])

    # --- backfill (portable correlated subqueries; every user has exactly one
    #     owner workspace after O-0, so each lookup resolves to a single value).
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE users SET active_workspace_id = ("
            "  SELECT wm.workspace_id FROM workspace_members wm"
            "  WHERE wm.user_id = users.id AND wm.role = 'owner'"
            ")"
        )
    )
    for table in LOG_TABLES:
        conn.execute(
            sa.text(
                f"UPDATE {table} SET workspace_id = ("
                "  SELECT wm.workspace_id FROM workspace_members wm"
                f"  WHERE wm.user_id = {table}.user_id AND wm.role = 'owner'"
                ")"
            )
        )


def downgrade() -> None:
    for table in LOG_TABLES:
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
    op.drop_table("workspace_invites")
    op.drop_column("users", "active_workspace_id")
