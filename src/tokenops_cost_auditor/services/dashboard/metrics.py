"""Owner-lens widget data (PLAN-V15 WP-2 / R-OWNER-LENS).

Each function returns ONE widget's data, so every widget can be re-rendered
independently as an htmx partial. Every payload carries `provenance` — the
audit id and timestamp the number came from — because determinism is a
design feature (R-DESIGN-SHELL §4): no figure appears without naming its
source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    AlertRule,
    Audit,
    CallAggregate,
    FindingFeedback,
    FindingRow,
    Source,
)
from tokenops_cost_auditor.services.dashboard.savings import SavingsSummary, compute

MONTH_DAYS = 30.0


@dataclass(frozen=True)
class Point:
    label: str
    value: float


@dataclass
class Widget:
    """One widget's payload. `empty` drives the designed empty state."""

    empty: bool = True
    provenance: str = "No audits yet"
    data: dict[str, object] = field(default_factory=dict)
    series: list[Point] = field(default_factory=list)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def latest_audit(session: Session, user_id: str) -> Audit | None:
    return session.execute(
        select(Audit)
        .where(Audit.user_id == user_id, Audit.status == "done")
        .order_by(Audit.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _stamp(audit: Audit | None) -> str:
    if audit is None:
        return "No audits yet"
    when = _aware(audit.report_ready_at or audit.created_at)
    return f"Audit {audit.id[:4]}…{audit.id[-3:]} · {when:%Y-%m-%d %H:%M} UTC"


def savings(session: Session, user_id: str) -> tuple[Widget, SavingsSummary]:
    audit = latest_audit(session, user_id)
    s = compute(session, user_id)
    w = Widget(
        empty=audit is None,
        provenance=_stamp(audit),
        data={
            "verified": s.verified_usd,
            "identified": s.identified_usd,
            "customer_reported": s.customer_reported_usd,
            "verified_count": s.verified_count,
            "pending_count": s.pending_count,
        },
    )
    return w, s


def spend_trend(session: Session, user_id: str) -> Widget:
    audit = latest_audit(session, user_id)
    if audit is None:
        return Widget()
    rows = (
        session.execute(select(CallAggregate).where(CallAggregate.audit_id == audit.id))
        .scalars()
        .all()
    )
    by_day: dict[str, float] = {}
    for r in rows:
        if r.cost_usd is not None:
            key = str(r.day)
            by_day[key] = by_day.get(key, 0.0) + float(r.cost_usd)
    series = [Point(d, v) for d, v in sorted(by_day.items())]
    run_rate = float(audit.total_spend_usd or 0.0) * MONTH_DAYS / max(audit.observed_days or 1, 1)
    return Widget(
        empty=not series,
        provenance=_stamp(audit),
        data={"run_rate_usd": round(run_rate, 2), "days": audit.observed_days or 0},
        series=series,
    )


def waste_trend(session: Session, user_id: str) -> Widget:
    audits = (
        session.execute(
            select(Audit)
            .where(Audit.user_id == user_id, Audit.status == "done")
            .order_by(Audit.created_at)
        )
        .scalars()
        .all()
    )
    series = [
        Point(f"{_aware(a.created_at):%b %d}", round(float(a.savings_pct or 0.0), 1))
        for a in audits
        if a.savings_pct is not None
    ]
    latest = audits[-1] if audits else None
    return Widget(
        empty=not series,
        provenance=_stamp(latest),
        data={"current_pct": series[-1].value if series else 0.0},
        series=series,
    )


def top_findings(session: Session, user_id: str, limit: int = 5) -> Widget:
    audit = latest_audit(session, user_id)
    if audit is None:
        return Widget()
    rows = (
        session.execute(
            select(FindingRow)
            .where(FindingRow.audit_id == audit.id)
            .order_by(FindingRow.monthly_impact_usd.desc())
        )
        .scalars()
        .all()
    )
    verdicts = {
        fb.finding_id: fb.verdict
        for fb in session.execute(
            select(FindingFeedback).where(FindingFeedback.audit_id == audit.id)
        )
        .scalars()
        .all()
    }
    items = [
        {
            "audit_id": audit.id,
            "finding_id": r.finding_id,
            "detector": r.detector,
            "severity": r.severity,
            "confidence": r.confidence,
            "monthly_usd": round(float(r.monthly_impact_usd), 2),
            "verdict": verdicts.get(r.finding_id),
        }
        for r in rows[:limit]
    ]
    return Widget(
        empty=not items,
        provenance=f"{len(rows)} findings · {_stamp(audit)}",
        data={"items": items, "total": len(rows)},
    )


def sources_health(session: Session, user_id: str, now: datetime | None = None) -> Widget:
    now = now or datetime.now(UTC)
    rows = (
        session.execute(
            select(Source)
            .where(Source.user_id == user_id, Source.status != "revoked")
            .order_by(Source.created_at)
        )
        .scalars()
        .all()
    )
    items = []
    for s in rows:
        stale = s.last_pull_at is None or (now - _aware(s.last_pull_at)) > timedelta(days=2)
        items.append(
            {
                "id": s.id,
                "provider": s.provider,
                "label": s.label,
                "status": s.status,
                "healthy": not stale and s.status == "active",
                "last_pull": (
                    f"{_aware(s.last_pull_at):%Y-%m-%d %H:%M} UTC" if s.last_pull_at else "never"
                ),
            }
        )
    return Widget(
        empty=not items,
        provenance=f"{len(items)} connection(s)",
        data={"items": items},
    )


def next_audit(session: Session, user_id: str, now: datetime | None = None) -> Widget:
    now = now or datetime.now(UTC)
    sources = (
        session.execute(select(Source).where(Source.user_id == user_id, Source.status == "active"))
        .scalars()
        .all()
    )
    due = [
        _aware(s.last_audit_at) + timedelta(days=7) for s in sources if s.last_audit_at is not None
    ]
    if not due:
        return Widget(empty=True, provenance="No scheduled audits")
    soonest = min(due)
    delta = soonest - now
    if delta.total_seconds() < 0:
        # Overdue is exactly what this widget exists to surface — never hide it
        # behind "today" (V-D4 cold-review f.5).
        late = abs(delta.days) or 1
        return Widget(
            empty=False,
            provenance=f"Was due {soonest:%a %d %b %H:%M} UTC · check the scheduler",
            data={"countdown": f"{late} day(s) overdue", "overdue": True},
        )
    days = delta.days
    label = "today" if days == 0 else ("1 day" if days == 1 else f"{days} days")
    return Widget(
        empty=False,
        provenance=f"Weekly cadence · next {soonest:%a %d %b %H:%M} UTC",
        data={"countdown": label, "overdue": False},
    )


def alerts_armed(session: Session, user_id: str, watching: bool = True) -> Widget:
    """Prevent stage + alerts widget. Rendered from real rules only: with none
    configured this says so plainly — it never promises a future feature
    (no-promises law, R-DESIGN-SHELL §1)."""
    if not watching:
        # §5 honesty: dispatch skips this plan entirely, so "N armed · checked
        # hourly" would be a false statement even if saved rules exist.
        return Widget(
            empty=True,
            provenance="Alerts are part of Pro — nothing is watched on this plan",
            data={"count": 0, "rules": []},
        )
    rows = (
        session.execute(select(AlertRule).where(AlertRule.user_id == user_id, AlertRule.enabled))
        .scalars()
        .all()
    )
    return Widget(
        empty=not rows,
        provenance=(f"{len(rows)} rule(s) armed · checked hourly" if rows else "No rules set up"),
        data={"count": len(rows), "rules": [r.rule for r in rows]},
    )


def yesterday_spend(
    session: Session, table: object, user_id: str, now: datetime | None = None
) -> Widget:
    """R-DAILY-LOOP: the morning-check tile. Same rate math as the digest and
    the source audit (daily.spend_between), so no two surfaces ever disagree.
    Honest zero: a connected account with a quiet day shows $0.00 — only an
    account with no sources gets the empty state."""
    from tokenops_cost_auditor.services.alerts.rules import SOFT_BUDGET
    from tokenops_cost_auditor.services.connectors import daily as daily_svc

    now = now or datetime.now(UTC)
    today = now.date()
    yday = today - timedelta(days=1)
    sources = (
        session.execute(select(Source).where(Source.user_id == user_id, Source.status == "active"))
        .scalars()
        .all()
    )
    if not sources:
        return Widget(empty=True, provenance="No connected sources")
    day = daily_svc.spend_between(session, table, user_id, yday, yday)  # type: ignore[arg-type]
    mtd = daily_svc.spend_between(session, table, user_id, today.replace(day=1), yday)  # type: ignore[arg-type]
    rule = session.execute(
        select(AlertRule).where(AlertRule.user_id == user_id, AlertRule.rule == SOFT_BUDGET)
    ).scalar_one_or_none()
    budget = float(rule.threshold) if rule is not None and rule.enabled and rule.threshold else None
    # Honesty (readiness audit): the tile priced only models on the verified
    # rate card and silently dropped the rest while claiming full coverage.
    # Name the excluded models so the total is never quietly understated.
    unpriced = sorted(day.unpriced)
    provenance = f"Daily usage pulls · priced on the verified rate card · {yday:%d %b}"
    if unpriced:
        provenance += f" · excludes unpriced: {', '.join(unpriced)}"
    return Widget(
        empty=False,
        provenance=provenance,
        data={
            "total": day.total_usd,
            "by_source": sorted(day.by_source.items(), key=lambda kv: -kv[1])[:3],
            "mtd": mtd.total_usd,
            "budget": budget,
            "budget_pct": (mtd.total_usd / budget * 100.0) if budget else None,
            "day_label": f"{yday:%d %b}",
            "unpriced": unpriced,
        },
    )


def onboarding(session: Session, user_id: str) -> dict:
    """The 5-step activation path (Wave A). Each step derives from data that
    already exists, so it self-completes as the customer progresses — the aha
    sequence: get data in → audit → review → apply → SEE a verified saving."""
    from sqlalchemy import func

    from tokenops_cost_auditor.services.dashboard.savings import compute

    has_source = (
        session.execute(
            select(func.count(Source.id)).where(
                Source.user_id == user_id, Source.status == "active"
            )
        ).scalar_one()
        > 0
    )
    audit_ids = list(
        session.execute(
            select(Audit.id).where(Audit.user_id == user_id, Audit.status == "done")
        ).scalars()
    )
    has_audit = len(audit_ids) > 0
    has_findings = has_audit and (
        session.execute(
            select(func.count(FindingRow.id)).where(FindingRow.audit_id.in_(audit_ids or [""]))
        ).scalar_one()
        > 0
    )
    applied = (
        session.execute(
            select(func.count(FindingFeedback.id)).where(
                FindingFeedback.audit_id.in_(audit_ids or [""]),
                FindingFeedback.verdict == "applied",
            )
        ).scalar_one()
        if has_audit
        else 0
    )
    verified = compute(session, user_id).verified_usd if has_audit else 0.0

    steps = [
        {
            "key": "connect",
            "label": "Connect a source (or upload a log file)",
            "done": has_source or has_audit,
            "href": "/sources",
            "cta": "Connect",
        },
        {
            "key": "audit",
            "label": "Run your first audit",
            "done": has_audit,
            "href": "/upload",
            "cta": "Start an audit",
        },
        {
            "key": "review",
            "label": "Review what it found, ranked by dollars",
            "done": has_findings,
            "href": "/findings",
            "cta": "See findings",
        },
        {
            "key": "apply",
            "label": "Apply a fix and mark it done",
            "done": applied > 0,
            "href": "/findings",
            "cta": "Apply a fix",
        },
        {
            "key": "verified",
            "label": "See a verified saving — proven on your next audit",
            "done": verified > 0,
            "href": "/dashboard",
            "cta": "Track savings",
        },
    ]
    done_n = sum(1 for s in steps if s["done"])
    # the first not-yet-done step is the single next-best-action
    nxt = next((s for s in steps if not s["done"]), None)
    return {
        "steps": steps,
        "done": done_n,
        "total": len(steps),
        "all_done": done_n == len(steps),
        "next": nxt,
    }
