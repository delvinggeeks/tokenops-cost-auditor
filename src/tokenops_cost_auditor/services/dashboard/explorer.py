"""FR-32 report explorer — compose a filtered view over ALL retained history.

Reads call_aggregates / findings / finding_feedback only — never raw uploads,
which purge on schedule (FR-21), so every filter works identically on purged
and unpurged audits (their derived aggregates are what we keep).

Overlap law (money-adjacent default, recorded in pricing_golden_NOTES.md):
when more than one audit in scope covers the same (day, model) bucket, the
most recent audit's rows win and the older rows are excluded from every
total — the aggregate-level analogue of the UAT-D5 "max-complete usage wins"
dedup. The page states this in words whenever it actually happened.

Findings de-dup rides the same key R-Q9 credits on: (detector, route) —
re-audits of the same route show once, most recent occurrence, with a
seen-in-N count.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import cast
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    Audit,
    CallAggregate,
    FindingFeedback,
    FindingRow,
    Source,
)

TIERS = ("all", "uploads", "connected")
GROUPS = ("auto", "day", "month")
STATUSES = ("any", "applied", "dismissed", "not_relevant", "unreviewed")
SEVERITIES = ("any", "high", "med", "low")
# Beyond this many distinct days, "auto" grouping rolls up to months.
AUTO_MONTH_SPAN_DAYS = 62
FINDINGS_CAP = 100


@dataclass(frozen=True)
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    group: str = "auto"
    tier: str = "all"
    # R-MULTI-SOURCE: a specific connected account. Set via the unified
    # `source` param; implies connected tier for the audit scope.
    source_id: str | None = None
    model: str | None = None
    detector: str | None = None
    severity: str = "any"
    status: str = "any"


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_filters(params: Mapping[str, str]) -> Filters:
    """Whitelist parsing: anything unrecognized falls back to the default —
    a hand-edited URL can never widen scope or crash the page."""
    tier = params.get("tier", "all")
    group = params.get("group", "auto")
    severity = params.get("severity", "any")
    status = params.get("status", "any")
    # Unified `source` select (R-MULTI-SOURCE): "", "uploads", "connected",
    # or a specific source id. An unknown id scopes to that id and matches
    # nothing — a hand-edited value can narrow, never widen.
    source = params.get("source", "")
    source_id: str | None = None
    if source in ("uploads", "connected"):
        tier = source
    elif source:
        source_id = source
        tier = "connected"
    return Filters(
        date_from=_parse_date(params.get("from")),
        date_to=_parse_date(params.get("to")),
        group=group if group in GROUPS else "auto",
        tier=tier if tier in TIERS else "all",
        source_id=source_id,
        model=params.get("model") or None,
        detector=params.get("detector") or None,
        severity=severity if severity in SEVERITIES else "any",
        status=status if status in STATUSES else "any",
    )


def serialize_filters(f: Filters) -> str:
    """Canonical querystring of the NON-DEFAULT filters — what a saved view
    stores (FR-32 C3). Round-trips through parse_filters, so a stored view
    can only ever contain whitelisted keys and values."""
    parts: list[tuple[str, str]] = []
    if f.date_from:
        parts.append(("from", f.date_from.isoformat()))
    if f.date_to:
        parts.append(("to", f.date_to.isoformat()))
    if f.group != "auto":
        parts.append(("group", f.group))
    if f.source_id:
        parts.append(("source", f.source_id))
    elif f.tier != "all":
        parts.append(("source", f.tier))
    if f.model:
        parts.append(("model", f.model))
    if f.detector:
        parts.append(("detector", f.detector))
    if f.severity != "any":
        parts.append(("severity", f.severity))
    if f.status != "any":
        parts.append(("status", f.status))
    return urlencode(parts)


@dataclass
class ModelRow:
    model: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class PeriodRow:
    period: str
    calls: int = 0
    cost_usd: float = 0.0


@dataclass
class ExplorerView:
    filters: Filters
    group: str = "day"  # resolved (auto -> day|month)
    spend_usd: float = 0.0
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    days_covered: int = 0
    unpriced_calls: int = 0
    audits_in_view: int = 0
    purged_in_view: int = 0
    connected_in_view: int = 0
    overlap_buckets: int = 0
    equiv_any: bool = False
    waste_monthly_usd: float = 0.0
    # R-MULTI-SOURCE: connected audits from before attribution shipped that a
    # per-account view necessarily excludes — stated on the page, never silent.
    unattributed_connected: int = 0
    # R-SYSTEM-TEST gate f.1: audits with findings but no per-day aggregate
    # rows are IN view (their findings are real and the dashboard counts
    # them); they contribute no spend/day data, which the page states.
    no_breakdown_in_view: int = 0
    by_model: list[ModelRow] = field(default_factory=list)
    by_period: list[PeriodRow] = field(default_factory=list)
    findings: list[dict[str, object]] = field(default_factory=list)
    findings_total: int = 0
    model_options: list[str] = field(default_factory=list)
    detector_options: list[str] = field(default_factory=list)
    # (id, label, status) per source the user has ever connected — revoked
    # accounts stay selectable; their audited history is still theirs.
    source_options: list[tuple[str, str, str]] = field(default_factory=list)


def _audit_when(a: Audit) -> datetime:
    return a.report_ready_at or a.created_at


def _day(r: CallAggregate) -> date:
    # models.py types the Date column as Mapped[object]; it is always a date.
    return cast(date, r.day)


def _scope_audits(session: Session, user_id: str, f: Filters) -> list[Audit]:
    audits = list(
        session.execute(select(Audit).where(Audit.user_id == user_id, Audit.status == "done"))
        .scalars()
        .all()
    )
    if f.source_id:
        audits = [a for a in audits if a.source_id == f.source_id]
    elif f.tier == "connected":
        audits = [a for a in audits if a.paid_via == "subscription"]
    elif f.tier == "uploads":
        audits = [a for a in audits if a.paid_via != "subscription"]
    return audits


def _latest_verdicts(session: Session, audit_ids: list[str]) -> dict[tuple[str, str], str]:
    """Latest verdict per (detector, route) across the given audits — the
    same route-identity resolution the findings drawer uses (R-Q9 key)."""
    if not audit_ids:
        return {}
    rows = (
        session.execute(select(FindingRow).where(FindingRow.audit_id.in_(audit_ids)))
        .scalars()
        .all()
    )
    key_of = {(r.audit_id, r.finding_id): (r.detector, r.route or r.finding_id) for r in rows}
    latest: dict[tuple[str, str], tuple[datetime, str]] = {}
    feedback = (
        session.execute(select(FindingFeedback).where(FindingFeedback.audit_id.in_(audit_ids)))
        .scalars()
        .all()
    )
    for fb in feedback:
        key = key_of.get((fb.audit_id, fb.finding_id))
        if key is None:
            continue
        if key not in latest or fb.ts > latest[key][0]:
            latest[key] = (fb.ts, fb.verdict)
    return {key: verdict for key, (_, verdict) in latest.items()}


def compose(session: Session, user_id: str, f: Filters) -> ExplorerView:
    view = ExplorerView(filters=f)
    view.source_options = [
        (s.id, s.label, s.status)
        for s in session.execute(
            select(Source).where(Source.user_id == user_id).order_by(Source.created_at)
        ).scalars()
    ]
    if f.source_id:
        # Bounded by the active date window (cold-review f.3): a "N audits
        # excluded" warning must describe THIS slice, not all of history.
        unattributed_ids = [
            a.id
            for a in session.execute(
                select(Audit).where(
                    Audit.user_id == user_id,
                    Audit.status == "done",
                    Audit.paid_via == "subscription",
                )
            ).scalars()
            if a.source_id is None
        ]
        if unattributed_ids and (f.date_from or f.date_to):
            in_window: set[str] = set()
            for row in session.execute(
                select(CallAggregate).where(CallAggregate.audit_id.in_(unattributed_ids))
            ).scalars():
                d = _day(row)
                if f.date_from and d < f.date_from:
                    continue
                if f.date_to and d > f.date_to:
                    continue
                in_window.add(row.audit_id)
            view.unattributed_connected = len(in_window)
        else:
            view.unattributed_connected = len(unattributed_ids)
    audits = _scope_audits(session, user_id, f)
    if not audits:
        return view
    by_id = {a.id: a for a in audits}
    # Recency rank: index 0 = most recent — the winner on overlapping buckets.
    # (id tiebreak, cold-review f.1: two audits can share report_ready_at on
    # batch/backfill runs; without it the money-adjacent overlap law would
    # resolve by arbitrary DB return order.)
    ranked = sorted(audits, key=lambda a: (_audit_when(a), a.id), reverse=True)
    rank = {a.id: i for i, a in enumerate(ranked)}

    aggs = list(
        session.execute(select(CallAggregate).where(CallAggregate.audit_id.in_(by_id)))
        .scalars()
        .all()
    )
    view.model_options = sorted({r.model for r in aggs})
    covered_ids = {r.audit_id for r in aggs}

    if f.date_from:
        aggs = [r for r in aggs if _day(r) >= f.date_from]
    if f.date_to:
        aggs = [r for r in aggs if _day(r) <= f.date_to]
    if f.model:
        aggs = [r for r in aggs if r.model == f.model]

    # Overlap law: latest audit wins per (day, model) bucket.
    best: dict[tuple[date, str], int] = {}
    for r in aggs:
        key = (_day(r), r.model)
        prev = best.get(key)
        if prev is None or rank[r.audit_id] < prev:
            best[key] = rank[r.audit_id]
    surviving = [r for r in aggs if rank[r.audit_id] == best[(_day(r), r.model)]]
    shadowed = {(_day(r), r.model) for r in aggs if rank[r.audit_id] != best[(_day(r), r.model)]}
    view.overlap_buckets = len(shadowed)

    models: dict[str, ModelRow] = {}
    periods: dict[str, PeriodRow] = {}
    days: set[date] = set()
    in_view_ids: set[str] = set()
    span_days = 0
    if surviving:
        all_days = sorted({_day(r) for r in surviving})
        span_days = (all_days[-1] - all_days[0]).days + 1
    view.group = (
        f.group
        if f.group in ("day", "month")
        else ("month" if span_days > AUTO_MONTH_SPAN_DAYS else "day")
    )
    for r in surviving:
        in_view_ids.add(r.audit_id)
        days.add(_day(r))
        view.calls += r.calls
        view.prompt_tokens += r.prompt_tokens
        view.completion_tokens += r.completion_tokens
        view.cached_tokens += r.cached_tokens
        if r.cost_usd is None:
            view.unpriced_calls += r.calls
        else:
            view.spend_usd += float(r.cost_usd)
        m = models.setdefault(r.model, ModelRow(model=r.model))
        m.calls += r.calls
        m.prompt_tokens += r.prompt_tokens
        m.completion_tokens += r.completion_tokens
        m.cached_tokens += r.cached_tokens
        m.cost_usd += float(r.cost_usd or 0.0)
        pkey = f"{_day(r):%Y-%m}" if view.group == "month" else str(_day(r))
        p = periods.setdefault(pkey, PeriodRow(period=pkey))
        p.calls += r.calls
        p.cost_usd += float(r.cost_usd or 0.0)

    # R-SYSTEM-TEST gate f.1 (first system-tester run, 2026-07-23): an audit
    # with findings but NO aggregate rows must not vanish — the dashboard
    # counts its findings, and a surface that contradicts another surface is
    # a FAIL by the sweep's law. A model slice is the one filter only
    # aggregate rows can answer, so bare audits stay out of model views.
    if not f.model:
        for a in audits:
            if a.id in covered_ids:
                continue
            when = _audit_when(a).date()
            if f.date_from and when < f.date_from:
                continue
            if f.date_to and when > f.date_to:
                continue
            in_view_ids.add(a.id)
            view.no_breakdown_in_view += 1

    view.days_covered = len(days)
    view.by_model = sorted(models.values(), key=lambda m: (-m.cost_usd, m.model))
    view.by_period = sorted(periods.values(), key=lambda p: p.period)

    in_view = [by_id[i] for i in in_view_ids]
    view.audits_in_view = len(in_view)
    view.purged_in_view = sum(1 for a in in_view if a.purged_at is not None)
    view.connected_in_view = sum(1 for a in in_view if a.paid_via == "subscription")
    view.equiv_any = any(a.equiv_spend for a in in_view)

    frows = (
        list(
            session.execute(select(FindingRow).where(FindingRow.audit_id.in_(in_view_ids)))
            .scalars()
            .all()
        )
        if in_view_ids
        else []
    )
    view.detector_options = sorted({fr.detector for fr in frows})
    if f.detector:
        frows = [fr for fr in frows if fr.detector == f.detector]
    if f.severity != "any":
        frows = [fr for fr in frows if fr.severity == f.severity]
    if f.model:
        frows = [fr for fr in frows if fr.route == f.model]

    # Findings de-dup on the R-Q9 key: latest occurrence wins, count the rest.
    latest_rows: dict[tuple[str, str], FindingRow] = {}
    seen_in: dict[tuple[str, str], int] = {}
    # fr.id tiebreak (cold-review f.2): same-timestamp audits — and the
    # unconstrained possibility of two same-key findings inside ONE audit —
    # must resolve deterministically, never by DB return order.
    for fr in sorted(frows, key=lambda fr: (_audit_when(by_id[fr.audit_id]), fr.id)):
        fkey = (fr.detector, fr.route or fr.finding_id)
        latest_rows[fkey] = fr
        seen_in[fkey] = seen_in.get(fkey, 0) + 1

    verdicts = _latest_verdicts(session, list(in_view_ids))
    items: list[dict[str, object]] = []
    waste = 0.0
    for fkey, fr in latest_rows.items():
        verdict = verdicts.get(fkey)
        if f.status == "unreviewed" and verdict is not None:
            continue
        if f.status in ("applied", "dismissed", "not_relevant") and verdict != f.status:
            continue
        impact = round(float(fr.monthly_impact_usd), 2)
        waste += impact
        items.append(
            {
                "audit_id": fr.audit_id,
                "finding_id": fr.finding_id,
                "detector": fr.detector,
                "route": fr.route,
                "severity": fr.severity,
                "confidence": fr.confidence,
                "monthly_usd": impact,
                "verdict": verdict,
                "seen_in": seen_in[fkey],
            }
        )
    items.sort(key=lambda i: -cast(float, i["monthly_usd"]))
    view.findings_total = len(items)
    view.findings = items[:FINDINGS_CAP]
    view.waste_monthly_usd = round(waste, 2)
    view.spend_usd = round(view.spend_usd, 6)
    return view
