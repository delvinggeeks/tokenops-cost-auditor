"""Verified-savings computation (PLAN-V15 §0 R-Q9). MONEY MATH — exact-value
goldens in tests/test_verified_savings.py, derivation in the golden NOTES
sheet (CLAUDE.md rule 4).

Founder formula, verbatim:

    verified_savings(month) = Σ over findings with status=Applied of
        max(0, baseline_monthly_impact - recomputed_impact_same_detector_and_route)

    counted ONLY after ≥1 post-application audit covering ≥7 days of data;
    per-finding verified amount capped at its original estimate.

Two rails that follow from the ruling and are enforced here:
  * manual savings-realized entries are returned SEPARATELY as
    customer_reported — they never enter `verified`;
  * unapplied findings are `identified`, never savings.

"Same detector and route" is keyed on (detector, route) where route is the
finding's detail["model"] when present, else its finding id — the stable
identity a re-audit reproduces for the same traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    Audit,
    FindingFeedback,
    FindingRow,
)

MIN_VERIFY_DAYS = 7  # R-Q9: a post-application audit must cover >= 7 days


@dataclass(frozen=True)
class SavingsSummary:
    verified_usd: float  # proven by re-audit (the headline)
    identified_usd: float  # open findings, still estimates
    customer_reported_usd: float  # self-reported, shown separately, never in the headline
    verified_count: int  # applied findings that have been re-audited
    pending_count: int  # applied but not yet re-audited (>=7 days)


def _route(detector: str, finding_id: str, detail: object) -> tuple[str, str]:
    if isinstance(detail, dict) and detail.get("model"):
        return (detector, str(detail["model"]))
    return (detector, finding_id)


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

    findings_by_audit: dict[str, list[FindingRow]] = {}
    for row in (
        session.execute(select(FindingRow).where(FindingRow.audit_id.in_([a.id for a in audits])))
        .scalars()
        .all()
    ):
        findings_by_audit.setdefault(row.audit_id, []).append(row)

    feedback = {
        (fb.audit_id, fb.finding_id): fb
        for fb in session.execute(
            select(FindingFeedback).where(FindingFeedback.audit_id.in_([a.id for a in audits]))
        )
        .scalars()
        .all()
    }

    latest = audits[-1]
    latest_by_route = {
        _route(f.detector, f.finding_id, None): f.monthly_impact_usd
        for f in findings_by_audit.get(latest.id, [])
    }

    verified = 0.0
    customer_reported = 0.0
    verified_count = 0
    pending_count = 0

    for audit in audits:
        for finding in findings_by_audit.get(audit.id, []):
            fb = feedback.get((audit.id, finding.finding_id))
            if fb is None:
                continue
            if fb.savings_realized_usd:
                # customer-reported: separate line, never the headline (R-Q9)
                customer_reported += float(fb.savings_realized_usd)
            if fb.verdict != "applied":
                continue
            # A later audit must exist AND cover >= 7 days of data
            qualifying = [
                a
                for a in audits
                if _aware(a.created_at) > _aware(fb.ts)  # ran AFTER the fix was applied
                and (a.observed_days or 0) >= MIN_VERIFY_DAYS  # and covers >= 7 days
            ]
            if not qualifying:
                pending_count += 1
                continue
            baseline = float(finding.monthly_impact_usd)
            recomputed = float(
                latest_by_route.get(_route(finding.detector, finding.finding_id, None), 0.0)
            )
            delta = max(0.0, baseline - recomputed)
            verified += min(delta, baseline)  # capped at the original estimate
            verified_count += 1

    identified = sum(
        float(f.monthly_impact_usd)
        for f in findings_by_audit.get(latest.id, [])
        if (latest.id, f.finding_id) not in feedback
        or feedback[(latest.id, f.finding_id)].verdict != "applied"
    )
    return SavingsSummary(
        verified_usd=round(verified, 2),
        identified_usd=round(identified, 2),
        customer_reported_usd=round(customer_reported, 2),
        verified_count=verified_count,
        pending_count=pending_count,
    )
