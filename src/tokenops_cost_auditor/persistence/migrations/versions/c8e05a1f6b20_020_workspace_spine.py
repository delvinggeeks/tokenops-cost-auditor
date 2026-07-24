"""020 workspace spine (O-0, R-ORG)

Revision ID: c8e05a1f6b20
Revises: b7d34e9a1c60
Create Date: 2026-07-24

Additive. The tenancy root: `workspaces` + `workspace_members`, and a
`workspace_id` on every directly-owned resource table. Backfill creates a
personal workspace-of-one (owner = the user) for every existing user and stamps
their resources with it — so single-tenant behavior is unchanged and O-1 can
re-scope reads to workspace_id without another migration. The audit ENGINE
never learns any of this (CLAUDE.md R-ORG): tenancy is a persistence/web fact.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "c8e05a1f6b20"
down_revision: str | None = "b7d34e9a1c60"
branch_labels: None = None
depends_on: None = None

# (table, owner-column) — the resources a workspace owns.
OWNED: list[tuple[str, str]] = [
    ("audits", "user_id"),
    ("sources", "user_id"),
    ("ingest_keys", "user_id"),
    ("api_tokens", "user_id"),
    ("oauth_apps", "owner_user_id"),
    ("saved_views", "user_id"),
    ("alert_rules", "user_id"),
    ("subscriptions", "user_id"),
    ("statements", "user_id"),
    ("devices", "user_id"),
]


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("personal", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(32),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(16), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )
    # At most ONE owner membership per user — the workspace-of-one 1:1 invariant
    # enforced in the DB (partial unique index, portable to both backends).
    op.create_index(
        "uq_owner_membership_per_user",
        "workspace_members",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
        sqlite_where=sa.text("role = 'owner'"),
    )

    for table, _owner in OWNED:
        op.add_column(table, sa.Column("workspace_id", sa.String(32), nullable=True))
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])

    # --- backfill: a personal workspace-of-one per user, then stamp resources.
    conn = op.get_bind()
    users = conn.execute(sa.text("SELECT id, email, created_at FROM users")).fetchall()
    for u in users:
        ws_id = uuid.uuid4().hex
        name = (f"{u.email}'s workspace")[:80]
        conn.execute(
            sa.text(
                "INSERT INTO workspaces (id, name, personal, created_at) "
                "VALUES (:id, :name, :personal, :created_at)"
            ),
            {"id": ws_id, "name": name, "personal": True, "created_at": u.created_at},
        )
        conn.execute(
            sa.text(
                "INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at) "
                "VALUES (:id, :w, :u, :role, :created_at)"
            ),
            {
                "id": uuid.uuid4().hex,
                "w": ws_id,
                "u": u.id,
                "role": "owner",
                "created_at": u.created_at,
            },
        )
        for table, owner in OWNED:
            conn.execute(
                sa.text(f"UPDATE {table} SET workspace_id = :w WHERE {owner} = :u"),
                {"w": ws_id, "u": u.id},
            )


def downgrade() -> None:
    for table, _owner in OWNED:
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
    op.drop_index("uq_owner_membership_per_user", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
