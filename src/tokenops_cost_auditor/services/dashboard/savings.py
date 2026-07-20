"""Verified-savings computation (PLAN-V15 §0 R-Q9). MONEY MATH — exact-value
goldens in tests/test_verified_savings.py, derivation in the golden NOTES
sheet (CLAUDE.md rule 4).

Founder formula, verbatim:

    verified_savings(month) = Σ over findings with status=Applied of
        max(0, baseline_monthly_impact - recomputed_impact_same_detector_and_route)

    counted ONLY after >=1 post-application audit covering >=7 days of data;
    per-finding verified amount capped at its original estimate.

Three correctness rules the ruling implies, each pinned by a test after the
V-D4 cold-review FAIL (2026-07-21):

  R1 ONE CREDIT PER ROUTE. Weekly audits re-emit the same finding while it
     remains unfixed, and each audit carries its own feedback row. Summing
     those would bill the same dollars every week, so a route is credited
     ONCE, against its EARLIEST applied feedback (the baseline in force when
     the customer acted).

  R2 A VANISHED ROUTE IS NOT AUTOMATICALLY A FIXED ROUTE. If the later audit
     has no finding for the route, that counts as "recomputed = 0" only when
     the audit still SAW TRAFFIC on that route. No traffic means we cannot
     attribute the disappearance to the fix (retired feature, quiet week), so
     it stays pending rather than crediting the full baseline.

  R3 NO DOUBLE BOOKING. A route counted as verified or pending is excluded
     from `identified` — a finding is one of the three, never two.

Also, per the ruling's own rails: customer-reported entries never enter the
headline, and unapplied findings are `identified`, never savings.

Route identity = (detector, findings.route or finding_id). `route` is the
model id persisted by both audit producers; the finding id is the fallback
for detectors that name no model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    Audit,
    CallAggregate,
    FindingFeedback,
    FindingRow,
)

MIN_VERIFY_DAYS = 7  # R-Q9: a post-application audit must cover >= 7 days

RouteKey = tuple[str, str]


@dataclass(frozen=True)
class SavingsSummary:
    verified_usd: float  # proven by re-audit (the headline)
    identified_usd: float  # open findings, still estimates
    customer_reported_usd: float  # self-reported, shown separately, never in the headline
    verified_count: int  # routes whose saving a later audit confirmed
    pending_count: int  # applied, but not yet confirmable


def _route_key(detector: str, route: str | None, finding_id: str) -> RouteKey:
    return (detector, route or finding_id)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def compute(session: Session, user_id: str, now: datetime | None = None) -> SavingsSummary:
    now = now or datetime.now(UTC)
    audits = (
        session.execute(
            select(Audit)
            .where(Audit.user_id == user_id, Audit.status == "done")
            .order_by(Audit.created_at)
        )
        .scalars()
        .all()
    )
    if not audits:
        return SavingsSummary(0.0, 0.0, 0.0, 0, 0)
    audit_ids = [a.id for a in audits]

    findings_by_audit: dict[str, list[FindingRow]] = {}
    for row in (
        session.execute(select(FindingRow).where(FindingRow.audit_id.in_(audit_ids)))
        .scalars()
        .all()
    ):
        findings_by_audit.setdefault(row.audit_id, []).append(row)

    feedback = (
        session.execute(select(FindingFeedback).where(FindingFeedback.audit_id.in_(audit_ids)))
        .scalars()
        .all()
    )
    fb_by_key = {(fb.audit_id, fb.finding_id): fb for fb in feedback}

    # R1: collapse every applied feedback onto its route, keeping the earliest.
    applied: dict[RouteKey, tuple[FindingRow, FindingFeedback]] = {}
    for audit in audits:
        for finding in findings_by_audit.get(audit.id, []):
            fb = fb_by_key.get((audit.id, finding.finding_id))
            if fb is None or fb.verdict != "applied":
                continue
            key = _route_key(finding.detector, finding.route, finding.finding_id)
            current = applied.get(key)
            if current is None or _aware(fb.ts) < _aware(current[1].ts):
                applied[key] = (finding, fb)

    verified = 0.0
    verified_count = 0
    pending_count = 0
    settled: set[RouteKey] = set()

    for key, (finding, fb) in applied.items():
        settled.add(key)
        qualifying = [
            a
            for a in audits
            if _aware(a.created_at) > _aware(fb.ts)  # ran AFTER the fix was applied
            and (a.observed_days or 0) >= MIN_VERIFY_DAYS  # and covers >= 7 days
        ]
        if not qualifying:
            pending_count += 1
            continue
        check = qualifying[-1]  # the most recent qualifying audit
        by_key = {
            _route_key(f.detector, f.route, f.finding_id): f
            for f in findings_by_audit.get(check.id, [])
        }
        still_found = by_key.get(key)
        if still_found is not None:
            recomputed = float(still_found.monthly_impact_usd)
        elif _route_had_traffic(session, check, finding.route):
            recomputed = 0.0  # R2: gone, and the route was still running — fixed
        else:
            pending_count += 1  # R2: gone, but no traffic to attribute it to
            continue
        baseline = float(finding.monthly_impact_usd)
        verified += min(max(0.0, baseline - recomputed), baseline)
        verified_count += 1

    # R3: identified excludes anything already settled as verified or pending.
    latest = audits[-1]
    identified = 0.0
    for f in findings_by_audit.get(latest.id, []):
        key = _route_key(f.detector, f.route, f.finding_id)
        if key in settled:
            continue
        # No applied-verdict check needed: every applied route is already in
        # `settled` above, so reaching here means the route was never applied.
        identified += float(f.monthly_impact_usd)

    # Customer-reported: every entry the customer made, summed as entered.
    # Separate line by ruling — it never touches `verified`.
    customer_reported = sum(float(fb.savings_realized_usd or 0.0) for fb in feedback)

    return SavingsSummary(
        verified_usd=round(verified, 2),
        identified_usd=round(identified, 2),
        customer_reported_usd=round(customer_reported, 2),
        verified_count=verified_count,
        pending_count=pending_count,
    )


def _route_had_traffic(session: Session, audit: Audit, route: str | None) -> bool:
    """Did this audit observe calls on the route? Without a model we cannot
    check, so we answer False and stay conservative (the finding stays
    pending rather than crediting a disappearance we cannot explain)."""
    if not route:
        return False
    return (
        session.execute(
            select(CallAggregate.id)
            .where(CallAggregate.audit_id == audit.id, CallAggregate.model == route)
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )
