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
from typing import Any, cast

from sqlalchemy import func, select
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


def forecast(session: Session, table: object, user_id: str, now: datetime | None = None) -> Widget:
    """R-FLYWHEEL L3 (deterministic-now): before-the-invoice month-end projection
    + overspend anomaly. Alert-only (X-02 intact). Same coster as every other
    spend surface, so the forecast, the digest and the audit never disagree.
    Below its data threshold it returns the empty state with an honest basis,
    never a projection from noise (Honesty Law)."""
    from tokenops_cost_auditor.services import forecast as fc

    sources = (
        session.execute(select(Source).where(Source.user_id == user_id, Source.status == "active"))
        .scalars()
        .all()
    )
    if not sources:
        return Widget(empty=True, provenance="No connected sources")
    f = fc.project_cycle(session, table, user_id, now=now)  # type: ignore[arg-type]
    if not f.ready:
        # honest "building your forecast — needs ~N more days" basis
        return Widget(empty=True, provenance=f.basis)
    return Widget(
        empty=False,
        provenance=f.basis,
        data={
            "projected": f.projected_usd,
            "mtd": f.mtd_usd,
            "baseline": f.baseline_usd,
            "over_pct": f.over_pct,
            "anomaly": f.anomaly,
            "days_elapsed": f.days_elapsed,
            "days_in_month": f.days_in_month,
        },
    )


def onboarding(session: Session, user_id: str) -> dict[str, Any]:
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


def audit_clarity(session: Session, table: object, user_id: str) -> dict[str, Any]:
    """Why a page looks the way it does — so "no findings" is never confused
    with "no audit." Distinguishes: no audit yet · audit ran but the models
    aren't on our verified rate card (the gpt-4o-mini gap) · audit ran, priced,
    and genuinely found no waste · findings exist. (Founder incident 2026-07-22:
    a real connected audit showed the 'connect a source' empty state because
    its only model was unpriced, so it priced $0 and produced 0 findings.)"""
    from sqlalchemy import func

    from tokenops_cost_auditor.persistence.models import SourceUsage
    from tokenops_cost_auditor.services.pricing.table import PricingGapError

    audit = latest_audit(session, user_id)
    if audit is None:
        return {"state": "none"}
    nfindings = int(
        session.execute(
            select(func.count(FindingRow.id)).where(FindingRow.audit_id == audit.id)
        ).scalar_one()
    )
    if nfindings > 0:
        return {"state": "has_findings", "count": nfindings}
    if float(audit.total_spend_usd or 0) > 0:
        return {
            "state": "clean",
            "row_count": audit.row_count or 0,
            "spend": float(audit.total_spend_usd or 0),
        }
    # priced $0 with rows analyzed → the models are unpriced. Name them.
    pairs = session.execute(
        select(Source.provider, SourceUsage.model)
        .join(SourceUsage, SourceUsage.source_id == Source.id)
        .where(Source.user_id == user_id)
        .distinct()
    ).all()
    today = datetime.now(UTC).date()
    unpriced: list[str] = []
    for provider, model in pairs:
        try:
            table.rate(provider, model, today)  # type: ignore[attr-defined]
        except PricingGapError:
            if model not in unpriced:
                unpriced.append(model)
    if unpriced:
        return {"state": "unpriced", "models": unpriced, "row_count": audit.row_count or 0}
    return {"state": "clean", "row_count": audit.row_count or 0, "spend": 0.0}


def pipeline(
    session: Session, table: object, user_id: str, watching: bool = True
) -> dict[str, Any]:
    """W0 — the spine's five stages, computed LIVE (R-PIPELINE-LIVE, founder
    2026-07-23). While an audit is queued/processing the active stage goes
    `live` (the A6 status pulse) and the widget polls itself; idle stages
    state what HAS happened. "Waiting" is reserved for stages nothing has
    ever reached — the founder's ribbon read "Waiting" on Analyze beside 11
    findings because it keyed on widget emptiness (an unpriced audit empties
    the spend trend), not on the audit record itself."""
    src = sources_health(session, user_id)
    latest = latest_audit(session, user_id)
    clarity = audit_clarity(session, table, user_id)
    sav, _summary = savings(session, user_id)
    top = top_findings(session, user_id)
    armed = alerts_armed(session, user_id, watching=watching)
    in_flight = session.execute(
        select(Audit)
        .where(Audit.user_id == user_id, Audit.status.in_(("queued", "processing")))
        .order_by(Audit.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    n_sources = len(cast("list[object]", src.data["items"])) if not src.empty else 0

    if (
        in_flight is not None
        and in_flight.paid_via == "subscription"
        and (in_flight.status == "queued")
    ):
        input_stage = {
            "label": "Input",
            "state": "live",
            "value": "Pulling usage now",
            "note": src.provenance,
        }
    elif n_sources:
        input_stage = {
            "label": "Input",
            "state": "active",
            "value": f"{n_sources} source(s)",
            "note": src.provenance,
        }
    else:
        input_stage = {
            "label": "Input",
            "state": "waiting",
            "value": "Start here",
            "note": "Connect a provider or upload a log file",
        }

    if in_flight is not None:
        analyze = {
            "label": "Analyze",
            "state": "live",
            "value": (
                f"{in_flight.row_count:,} calls read"
                if in_flight.row_count is not None
                else ("Reading your data" if in_flight.status == "processing" else "Queued to run")
            ),
            "note": f"running now — audit {in_flight.id[:4]}…{in_flight.id[-3:]}",
        }
    elif latest is not None:
        value = f"{latest.row_count:,} calls" if latest.row_count is not None else "Analyzed"
        if latest.observed_days:
            value += f" · {latest.observed_days} day(s)"
        note = _stamp(latest)
        if clarity.get("state") == "unpriced":
            value += " — pricing pending"
            note = "models not on the rate card yet; we price and re-run automatically"
        analyze = {"label": "Analyze", "state": "active", "value": value, "note": note}
    else:
        analyze = {
            "label": "Analyze",
            "state": "waiting",
            "value": "Waiting",
            "note": "runs the moment data lands",
        }

    if latest is not None and not top.empty:
        report = {
            "label": "Report",
            "state": "active",
            "value": f"{top.data['total']} findings",
            "note": (
                # Scope stated in words (system-tester C3 walk f.1): this
                # figure is the LATEST audit's identified waste; the explorer
                # sums the whole slice — same word, different scope, so both
                # surfaces say WHICH or a founder reads a 3x contradiction.
                "${:,.2f}/mo identified — latest audit".format(cast(float, sav.data["identified"]))
                if not sav.empty
                else "Findings ranked by dollars"
            ),
        }
        if in_flight is not None:
            report["note"] = "refreshing — a new run is in progress"
    elif latest is not None:
        # An audit RAN — zero findings is a result, never "Waiting" (ux gate
        # f.1). And the claim is scoped OUT LOUD (system-tester sweep 2 f.1):
        # "clean" here means the LATEST audit; if history holds findings the
        # explorer will show, this stage says so instead of contradicting it.
        earlier = int(
            session.execute(
                select(func.count(FindingRow.id))
                .join(Audit, FindingRow.audit_id == Audit.id)
                .where(Audit.user_id == user_id)
            ).scalar_one()
        )
        history_note = (
            f"{earlier} earlier finding{'s' if earlier != 1 else ''} in your history — see Explore"
            if earlier
            else ""
        )
        if clarity.get("state") == "clean":
            report = {
                "label": "Report",
                "state": "active",
                "value": "0 new findings — latest audit clean" if earlier else "0 findings — clean",
                "note": history_note or "no avoidable waste found; we keep watching",
            }
        else:  # unpriced: no findings COULD land until the models are priced
            report = {
                "label": "Report",
                "state": "active",
                "value": "0 findings — pricing pending",
                "note": history_note or "findings land once the models are on the rate card",
            }
        if in_flight is not None:
            report["note"] = "refreshing — a new run is in progress"
    elif in_flight is not None:
        report = {
            "label": "Report",
            "state": "waiting",
            "value": "Lands when this run finishes",
            "note": "",
        }
    else:
        report = {
            "label": "Report",
            "state": "waiting",
            "value": "Waiting",
            "note": "Findings ranked by dollars",
        }

    # "N applied" counts APPLIED fixes (verified + still-measuring), not the
    # verified subset it mislabeled before (system-tester sweep 2 f.1: an
    # account with 1 applied finding read "0 applied"). The verified DOLLAR
    # stays R-Q9-pure; customer-reported money appears separately, labeled,
    # never in the verified figure.
    applied_n = int(cast(int, sav.data.get("verified_count", 0))) + int(
        cast(int, sav.data.get("pending_count", 0))
    )
    act_note = (
        "${:,.2f}/mo verified".format(cast(float, sav.data["verified"]))
        if not sav.empty
        else "Apply a fix, we verify the saving"
    )
    if not sav.empty and cast(float, sav.data.get("customer_reported", 0.0)):
        act_note += " · ${:,.2f}/mo customer-reported".format(
            cast(float, sav.data["customer_reported"])
        )
    act = {
        "label": "Act",
        "state": "active" if applied_n else "waiting",
        "value": f"{applied_n} applied",
        "note": act_note,
    }

    prevent = {
        "label": "Prevent",
        "state": "active" if not armed.empty else "waiting",
        "value": f"{armed.data['count']} armed" if not armed.empty else "Not set up",
        "note": armed.provenance,
    }

    return {
        "stages": [input_stage, analyze, report, act, prevent],
        "in_flight": in_flight is not None,
    }


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def benchmark(session: Session, settings: object, user_id: str) -> Widget:
    """M-FLY-1 L1: the customer's waste-share percentile among included
    customers. LEAKAGE LAW: this widget's data is {percentile, n} and
    nothing else — no other company's figure can render because no other
    company's figure leaves the service layer. Dormant (n below threshold,
    opted out, or unranked) = Widget.empty = the surface does not exist."""
    from tokenops_cost_auditor.config import Settings as _S
    from tokenops_cost_auditor.services.flywheel import benchmarks as bench

    b = bench.waste_percentile(session, cast(_S, settings), user_id)
    if not b.live or b.percentile is None:
        return Widget()
    return Widget(
        empty=False,
        provenance=f"based on {b.n} companies · your latest audit",
        data={
            "percentile": b.percentile,
            "label": _ordinal(b.percentile),
            "leaner_than": 100 - b.percentile,
            "n": b.n,
        },
    )
