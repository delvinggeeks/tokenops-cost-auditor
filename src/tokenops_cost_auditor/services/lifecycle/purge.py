"""Scheduled purge (FR-21): raw uploads removed purge_after_days after report
generation, daily via ofelia (`python -m tokenops_cost_auditor.services.lifecycle.purge`).

Due = report_ready_at older than the window; audits that never produced a report
(failed, stuck) fall back to created_at, so the FR-23 promise ("nothing retained
beyond 7 days") holds on failure paths too. Only the raw upload directory is
removed — derived aggregates (counts, no text; FR-22) and rendered reports stay.
Every purge appends to audit_log (FR-21).
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import Audit, IdempotencyKey
from tokenops_cost_auditor.services.lifecycle import auditlog

ACTOR = "system@purge"


def _as_utc(value: datetime) -> datetime:
    # sqlite returns naive datetimes; they are UTC by contract (NFR-11)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def due_audits(session: Session, purge_after_days: int, now: datetime) -> list[Audit]:
    """Un-purged audits whose retention window has elapsed (T-LIF-01)."""
    cutoff = now - timedelta(days=purge_after_days)
    candidates = session.scalars(
        select(Audit).where(Audit.purged_at.is_(None), Audit.upload_path.is_not(None))
    )
    return [a for a in candidates if _as_utc(a.report_ready_at or a.created_at) <= cutoff]


def purge_due(session: Session, purge_after_days: int, now: datetime | None = None) -> list[str]:
    """Purge every due audit; returns purged audit ids. Commits once at the end."""
    now = now or datetime.now(UTC)
    purged: list[str] = []
    for audit in due_audits(session, purge_after_days, now):
        if audit.upload_path:
            shutil.rmtree(Path(audit.upload_path).parent, ignore_errors=True)
        audit.upload_path = None
        audit.purged_at = now
        # FR-26: idempotency keys share the upload lifecycle — a replayed key
        # after purge is a fresh upload, not a stale replay
        session.execute(delete(IdempotencyKey).where(IdempotencyKey.audit_id == audit.id))
        auditlog.append(session, ACTOR, "audit.purged", audit.id, {"mode": "scheduled"})
        purged.append(audit.id)
    session.commit()
    return purged


def main() -> None:
    from tokenops_cost_auditor.config import Settings
    from tokenops_cost_auditor.persistence.repo import make_engine, make_session_factory

    settings = Settings()
    engine = make_engine(settings.database_url)
    with make_session_factory(engine)() as session:
        purged = purge_due(session, settings.purge_after_days)
    print(f"purge: {len(purged)} audit(s) purged: {', '.join(purged) or '-'}")


if __name__ == "__main__":
    main()
