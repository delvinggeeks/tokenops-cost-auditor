"""019 developer platform (S-6, R-SDK-PLATFORM)

Revision ID: b7d34e9a1c60
Revises: a3e59c7f24d1
Create Date: 2026-07-24

Additive only. The READ half of the platform: personal read-scoped API tokens
(rt_), registered OAuth applications, their single-use authorization codes, and
the read-scoped access tokens they issue. All credential columns are nullable
keyed HMACs — revoke DELETES the material and keeps the row for attribution
(authority-law parity with ingest_keys/devices).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b7d34e9a1c60"
down_revision: str | None = "a3e59c7f24d1"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("scopes", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "oauth_apps",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("client_id", sa.String(48), nullable=False, unique=True),
        sa.Column("client_secret_hash", sa.String(64), nullable=True),
        sa.Column("redirect_uris", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "oauth_auth_codes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "app_id",
            sa.String(32),
            sa.ForeignKey("oauth_apps.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(200), nullable=False, server_default=""),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "oauth_access_tokens",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "app_id",
            sa.String(32),
            sa.ForeignKey("oauth_apps.id", ondelete="CASCADE"),
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
        sa.Column("token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("scopes", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("oauth_access_tokens")
    op.drop_table("oauth_auth_codes")
    op.drop_table("oauth_apps")
    op.drop_table("api_tokens")
