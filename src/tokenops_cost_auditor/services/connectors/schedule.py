"""V-D3 scheduler core (PLAN-V15 WP-3a): ofelia hourly tick -> due work.

Deterministic and idempotent: due-ness derives ONLY from last_pull_at /
last_audit_at stamps, which run_pull/run_source_audit update in the same
transaction as their work — a repeated or overlapping tick recomputes "due"
as false and no-ops (the FR-26 idempotency posture for scheduled runs;
upserts make double pulls harmless anyway). Cadence per R-CONNECT: daily
pull, weekly auto-audit, active sources only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Source
from tokenops_cost_auditor.services.alerts import dispatch as alerts_dispatch
from tokenops_cost_auditor.services.connectors.pull import run_pull
from tokenops_cost_auditor.services.connectors.source_audit import run_source_audit
from tokenops_cost_auditor.services.payments import subscriptions
from tokenops_cost_auditor.services.pricing.table import PricingTable

log = structlog.get_logger("tokenops_cost_auditor.connectors")

PULL_EVERY = timedelta(days=1)
AUDIT_EVERY = timedelta(days=7)


def _aware(dt: datetime) -> datetime:
    """SQLite round-trips tz-aware columns as naive; Postgres keeps them aware.
    All stamps are written as UTC, so naive means UTC here."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def due_pulls(session: Session, now: datetime) -> list[Source]:
    sources = session.execute(select(Source).where(Source.status == "active")).scalars().all()
    return [
        s
        for s in sources
        if s.credentials_encrypted
        and (s.last_pull_at is None or now - _aware(s.last_pull_at) >= PULL_EVERY)
    ]


def due_audits(session: Session, now: datetime, settings: Settings | None = None) -> list[Source]:
    sources = session.execute(select(Source).where(Source.status == "active")).scalars().all()
    due = [
        s
        for s in sources
        # first audit only after the first pull has landed data
        if s.last_pull_at is not None
        and (s.last_audit_at is None or now - _aware(s.last_audit_at) >= AUDIT_EVERY)
    ]
    if settings is None:
        return due
    # R-Q12 day 7: a read-only account keeps its data, its dashboard and its
    # connections — only SCHEDULED audits pause. Pulls continue, so nothing
    # is lost while payment is sorted out.
    allowed = subscriptions.entitlements_for(session, settings, [s.user_id for s in due])
    return [s for s in due if allowed[s.user_id]["scheduled_audits"]]


def tick(
    session: Session,
    settings: Settings,
    table: PricingTable,
    now: datetime | None = None,
    mail: object | None = None,
) -> dict[str, int]:
    """One scheduler pass. Failures on one source never block the others."""
    now = now or datetime.now(UTC)
    stats = {"pulled": 0, "pull_errors": 0, "audited": 0, "audit_errors": 0}
    for source in due_pulls(session, now):
        try:
            run_pull(session, settings, source)
            session.commit()
            stats["pulled"] += 1
        except Exception as exc:
            session.rollback()
            stats["pull_errors"] += 1
            log.warning("connector.pull_failed", source_id=source.id, error=str(exc)[:200])
    for source in due_audits(session, now, settings):
        try:
            run_source_audit(session, settings, table, source)
            session.commit()
            stats["audited"] += 1
        except Exception as exc:
            session.rollback()
            stats["audit_errors"] += 1
            log.warning("connector.audit_failed", source_id=source.id, error=str(exc)[:200])
    if mail is not None:
        # Walk any failing subscription to the rung it has reached (R-Q12).
        try:
            dunning = subscriptions.advance_dunning(session, settings, mail, now=now)
            stats["dunning_moved"] = sum(dunning.values())
        except Exception as exc:
            session.rollback()
            stats["dunning_errors"] = 1
            log.warning("dunning.stage_failed", error=str(exc)[:200])
        # WP-3b: alerts are evaluated after audits land, so a new finding or a
        # spend jump reaches the customer in the same pass that discovered it.
        # Isolated like every other stage: pulls and audits are already
        # committed and must not be lost to an alerting failure (V-D5
        # cold-review f.4).
        try:
            alert_stats = alerts_dispatch.run_all(session, settings, mail, now=now)
            stats["alerts_fired"] = alert_stats["fired"]
            stats["alert_errors"] = alert_stats["errors"]
        except Exception as exc:
            session.rollback()
            stats["alert_errors"] = stats.get("alert_errors", 0) + 1
            log.warning("alert.stage_failed", error=str(exc)[:200])
    log.info("connector.tick", **stats)
    return stats
