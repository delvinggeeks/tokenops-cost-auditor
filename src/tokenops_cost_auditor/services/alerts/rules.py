"""Alert rules (PLAN-V15 WP-3b): the four rules the founder ruled, evaluated
against audits the customer already has.

OBSERVE ONLY (X-02): each evaluation returns a message or None. Nothing here
changes traffic, pauses a source, or touches a plan.

Every message states the number first (R-DESIGN §4e: the subject carries the
number) and names the audit it came from, because a figure without its
provenance is not something we print (R-DESIGN-SHELL §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    AlertEvent,
    AlertRule,
    Audit,
    FindingRow,
    User,
)

SPEND_SPIKE = "spend_spike_dod"
WASTE_ABOVE = "waste_above_target"
NEW_HIGH = "new_high_finding"
SOFT_BUDGET = "soft_budget"
RULES = (SPEND_SPIKE, WASTE_ABOVE, NEW_HIGH, SOFT_BUDGET)

RULE_LABELS = {
    SPEND_SPIKE: "Spend jumped versus the previous audit",
    WASTE_ABOVE: "Waste share above your target",
    NEW_HIGH: "A new high-impact finding appeared",
    SOFT_BUDGET: "Monthly spend crossed your budget",
}


@dataclass(frozen=True)
class Firing:
    rule: str
    subject: str  # the number leads
    body: str
    detail: dict[str, object]


def _monthly(audit: Audit) -> float:
    days = max(audit.observed_days or 1, 1)
    return float(audit.total_spend_usd or 0.0) * 30.0 / days


def _stamp(audit: Audit) -> str:
    when = audit.report_ready_at or audit.created_at
    return f"audit {audit.id[:4]}…{audit.id[-3:]} ({when:%Y-%m-%d %H:%M} UTC)"


def evaluate(
    session: Session, settings: Settings, user: User, now: datetime | None = None
) -> list[Firing]:
    """Evaluate every enabled rule for one user. Returns what should be sent;
    the caller decides delivery and records events (separation keeps this
    function pure enough to test without mail)."""
    now = now or datetime.now(UTC)
    audits = (
        session.execute(
            select(Audit)
            .where(Audit.user_id == user.id, Audit.status == "done")
            .order_by(Audit.created_at)
        )
        .scalars()
        .all()
    )
    if not audits:
        return []
    latest = audits[-1]
    previous = audits[-2] if len(audits) > 1 else None

    enabled = {
        r.rule: r
        for r in session.execute(
            select(AlertRule).where(AlertRule.user_id == user.id, AlertRule.enabled)
        )
        .scalars()
        .all()
    }
    already = {
        (e.rule, str(e.detail.get("audit_id")))
        for e in session.execute(select(AlertEvent).where(AlertEvent.user_id == user.id))
        .scalars()
        .all()
    }

    firings: list[Firing] = []

    def fire(rule: str, subject: str, body: str, detail: dict[str, object]) -> None:
        # One alert per rule per audit: a re-run must not re-send (FR-26 posture)
        if (rule, latest.id) in already:
            return
        firings.append(
            Firing(rule=rule, subject=subject, body=body, detail={**detail, "audit_id": latest.id})
        )

    if SPEND_SPIKE in enabled and previous is not None:
        threshold = enabled[SPEND_SPIKE].threshold or settings.alert_spend_spike_dod_pct
        before, after = _monthly(previous), _monthly(latest)
        if before > 0:
            change = (after - before) / before * 100.0
            if change >= threshold:
                fire(
                    SPEND_SPIKE,
                    f"${after:,.2f}/mo — your AI spend is up {change:.0f}%",
                    (
                        f"Your run-rate moved from ${before:,.2f} to ${after:,.2f} per month, "
                        f"a {change:.0f}% increase, between your last two audits.\n\n"
                        f"Source: {_stamp(latest)}.\n\n"
                        "Open your findings to see what changed."
                    ),
                    {"before": round(before, 2), "after": round(after, 2), "pct": round(change, 1)},
                )

    if WASTE_ABOVE in enabled:
        threshold = enabled[WASTE_ABOVE].threshold or settings.alert_waste_target_pct
        waste = float(latest.savings_pct or 0.0)
        if waste > threshold:
            fire(
                WASTE_ABOVE,
                f"{waste:.1f}% of your AI spend looks avoidable",
                (
                    f"Your latest audit puts avoidable spend at {waste:.1f}%, above the "
                    f"{threshold:.0f}% target you set.\n\n"
                    f"Source: {_stamp(latest)}.\n\n"
                    "The findings list is ranked by dollars — start at the top."
                ),
                {"waste_pct": round(waste, 1), "target": threshold},
            )

    if NEW_HIGH in enabled:
        latest_findings = (
            session.execute(select(FindingRow).where(FindingRow.audit_id == latest.id))
            .scalars()
            .all()
        )
        seen_before: set[tuple[str, str]] = set()
        if previous is not None:
            seen_before = {
                (f.detector, f.route or f.finding_id)
                for f in session.execute(
                    select(FindingRow).where(FindingRow.audit_id == previous.id)
                )
                .scalars()
                .all()
            }
        fresh = [
            f
            for f in latest_findings
            if f.severity == "high" and (f.detector, f.route or f.finding_id) not in seen_before
        ]
        if fresh:
            top = max(fresh, key=lambda f: f.monthly_impact_usd)
            fire(
                NEW_HIGH,
                f"${top.monthly_impact_usd:,.2f}/mo — a new high-impact finding",
                (
                    f"{len(fresh)} new high-impact finding(s) appeared in your latest audit. "
                    f"The largest is worth ${top.monthly_impact_usd:,.2f} per month.\n\n"
                    f"Source: {_stamp(latest)}.\n\n"
                    "Open it for the evidence and the fix."
                ),
                {"count": len(fresh), "top_usd": round(float(top.monthly_impact_usd), 2)},
            )

    if SOFT_BUDGET in enabled and enabled[SOFT_BUDGET].threshold:
        budget = float(enabled[SOFT_BUDGET].threshold or 0.0)
        spend = _monthly(latest)
        if spend > budget:
            fire(
                SOFT_BUDGET,
                f"${spend:,.2f}/mo — past your ${budget:,.2f} budget",
                (
                    f"Your run-rate is ${spend:,.2f} per month against the ${budget:,.2f} "
                    "budget you set.\n\n"
                    f"Source: {_stamp(latest)}.\n\n"
                    "This is a notification only — nothing has been paused or limited."
                ),
                {"spend": round(spend, 2), "budget": budget},
            )

    return firings
