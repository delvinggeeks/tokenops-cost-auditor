"""013 source attribution (R-MULTI-SOURCE, founder order 2026-07-23)

Additive, two columns:
- audits.source_id — which connected account produced the audit; NULL for
  uploads and for connected audits that predate this migration (those are
  honestly labeled "unattributed" wherever a per-account view is composed).
- sources.key_fingerprint — keyed one-way HMAC of the API key; blocks
  connecting the SAME key twice (double-counting guard) while allowing a
  second account of the same provider. NULL rows backfill on their next
  scheduled pull.

Revision ID: a7d40c91b3e5
Revises: e5b8c2f74a19
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d40c91b3e5"
down_revision: str | None = "e5b8c2f74a19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audits", sa.Column("source_id", sa.String(32), nullable=True))
    op.create_index("ix_audits_source_id", "audits", ["source_id"])
    op.add_column("sources", sa.Column("key_fingerprint", sa.String(64), nullable=True))
    op.create_index("ix_sources_key_fingerprint", "sources", ["key_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_sources_key_fingerprint", table_name="sources")
    op.drop_column("sources", "key_fingerprint")
    op.drop_index("ix_audits_source_id", table_name="audits")
    op.drop_column("audits", "source_id")
