"""R-FLYWHEEL Stage 3 / L3 (deterministic-now): before-the-invoice spend forecast
and mid-cycle overspend anomaly.

This is the honest, single-customer version of the Learning Ladder's L3 rung: it
projects the current billing month's end-of-cycle spend from the customer's OWN
history and flags a projected overspend BEFORE the invoice — no trained model, no
cross-customer data, no inference (NFR-01), counts-only (FR-22). It becomes the
substrate the trained L3 model (n>=50 + 6mo) refines later; the surface stays the
same, the engine sharpens.

HONESTY LAW (docs/12 Stage 3): every output prints its basis — days of the month
observed and the span of history behind the baseline. Below its data threshold it
says so plainly ("not enough history yet") rather than projecting from noise.

X-02 intact: this observes and alerts. It never blocks or enforces. All money math
runs through daily.spend_between (the audit's own coster), so the forecast, the
dashboard tile, the digest and the audit never disagree about a dollar.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import Source, SourceUsage
from tokenops_cost_auditor.services.pricing.table import PricingTable

# Data thresholds (Honesty Law): don't project from noise.
MIN_HISTORY_DAYS = 30  # need at least a month of history before a baseline is honest
MIN_ELAPSED_DAYS = 5  # need a few complete days this month before a projection means anything
BASELINE_WINDOW_DAYS = 90  # baseline = trailing quarter, averaged to a month
DEFAULT_OVERSPEND_PCT = 30.0


@dataclass(frozen=True)
class Forecast:
    ready: bool  # enough history + elapsed days for an honest projection
    mtd_usd: float  # spend so far this month (complete days only)
    projected_usd: float  # projected end-of-month spend at the current run-rate
    baseline_usd: float | None  # trailing-quarter average monthly spend
    over_pct: float | None  # projected vs baseline (+ = trending high)
    anomaly: bool  # projected overspend beyond threshold -> fire the alert
    days_elapsed: int  # complete days observed this month
    days_in_month: int
    history_days: int  # span of usage history behind the baseline
    basis: str  # human-readable Honesty-Law basis line
    baseline_partial: bool = False  # baseline window had unpriced usage (understated)
    mtd_partial: bool = False  # current month had unpriced usage (projection understated)
    reason: str = ""  # why not ready, when ready is False


def _earliest_usage_day(session: Session, user_id: str) -> date | None:
    return session.execute(
        select(func.min(SourceUsage.day))
        .join(Source, SourceUsage.source_id == Source.id)
        .where(Source.user_id == user_id)
    ).scalar_one_or_none()


def project_cycle(
    session: Session,
    table: PricingTable,
    user_id: str,
    now: datetime | None = None,
    threshold_pct: float = DEFAULT_OVERSPEND_PCT,
) -> Forecast:
    """Project this calendar month's end-of-cycle spend and flag a projected
    overspend vs the trailing-quarter average. Complete days only (today is
    partial, so it is excluded from both the run-rate and the baseline)."""
    from tokenops_cost_auditor.services.connectors import daily as daily_svc

    now = now or datetime.now(UTC)
    today = now.date()
    month_start = today.replace(day=1)
    yesterday = today - timedelta(days=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_elapsed = (yesterday - month_start).days + 1 if yesterday >= month_start else 0

    earliest = _earliest_usage_day(session, user_id)
    history_days = (yesterday - earliest).days + 1 if earliest is not None else 0

    mtd_spend = (
        daily_svc.spend_between(session, table, user_id, month_start, yesterday)
        if days_elapsed > 0
        else None
    )
    mtd = mtd_spend.total_usd if mtd_spend is not None else 0.0
    # Symmetric honesty to the baseline guard below (cold-review f.1): unpriced
    # usage THIS month understates mtd/projected. The alert may still fire — an
    # understated projection crossing the threshold is conservative-safe — but
    # the number must never present as complete when it isn't.
    mtd_partial = bool(mtd_spend.unpriced) if mtd_spend is not None else False
    projected = (mtd / days_elapsed * days_in_month) if days_elapsed > 0 else 0.0

    # Baseline: the trailing quarter BEFORE this month, averaged to a month.
    base_end = month_start - timedelta(days=1)
    base_start = base_end - timedelta(days=BASELINE_WINDOW_DAYS - 1)
    base_spend = daily_svc.spend_between(session, table, user_id, base_start, base_end)
    base_total = base_spend.total_usd
    # If part of the baseline window is unpriced (usage of models the rate card
    # didn't cover on those dates), the baseline is UNDERSTATED — projecting an
    # "overspend" against it would be a false alarm. Show the projection, hold
    # the alert, and say so.
    baseline_partial = bool(base_spend.unpriced)
    baseline: float | None = (
        base_total / (BASELINE_WINDOW_DAYS / 30.0)
        if history_days >= MIN_HISTORY_DAYS and base_total > 0
        else None
    )

    over_pct = ((projected - baseline) / baseline * 100.0) if baseline else None
    ready = (
        history_days >= MIN_HISTORY_DAYS
        and days_elapsed >= MIN_ELAPSED_DAYS
        and baseline is not None
    )
    anomaly = bool(
        ready and not baseline_partial and over_pct is not None and over_pct >= threshold_pct
    )

    if ready:
        reason = ""
        basis = (
            f"projected from {days_elapsed} of {days_in_month} days this month, "
            f"against your prior {BASELINE_WINDOW_DAYS}-day average "
            f"(history: {history_days} days)"
        )
        if baseline_partial:
            basis += " — baseline still filling in, so we hold the overspend alert"
        if mtd_partial:
            basis += (
                " — some of this month's usage isn't priced yet, so the projection "
                "is understated"
            )
    else:
        if history_days < MIN_HISTORY_DAYS:
            reason = f"needs ~{MIN_HISTORY_DAYS - history_days} more day(s) of history"
        elif days_elapsed < MIN_ELAPSED_DAYS:
            reason = f"needs {MIN_ELAPSED_DAYS - days_elapsed} more day(s) into the month"
        else:
            reason = "no prior spend to compare against yet"
        basis = f"building your forecast — {reason}"

    return Forecast(
        ready=ready,
        mtd_usd=mtd,
        projected_usd=projected,
        baseline_usd=baseline,
        over_pct=over_pct,
        anomaly=anomaly,
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        history_days=history_days,
        basis=basis,
        baseline_partial=baseline_partial,
        mtd_partial=mtd_partial,
        reason=reason,
    )
