"""T2 source audit: accumulated source_usage buckets -> reduced-detector
audit + report.json (PLAN-V15 WP-1/V-D3; R-Q1 honest coverage).

Assembles ReportModel DIRECTLY (not ReportModel.build): bucket rows are not
call records, and the upload builder would misreport bucket counts as call
counts. Same dataclass, same renderer, same persistence tables — only the
assembly respects aggregate semantics: row_count = SUM of provider-reported
calls; spend is the as-billed bucket cost at the verified rate card;
unpriced models are listed, never guessed (FR-28 discipline; a model
unpriced here is the same model the estimators skipped — one FR-28
surface). An unpriced DOWNGRADE TARGET makes d1 skip conservatively and
does not appear in unpriced_models (it carries no usage). Inactive
detectors (D4/D5/D6) land in report.coverage as labeled rows carrying NO
savings number, each with the one-line upgrade path (R-Q1 law). Every run
creates a NEW audit: the weekly series is deliberate history for the
dashboard trend, not an idempotent overwrite.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pandas as pd
import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    Audit,
    CallAggregate,
    FindingRow,
    Source,
    SourceUsage,
    StageEvent,
    utcnow,
)
from tokenops_cost_auditor.services.flywheel import benchmarks as flywheel_benchmarks
from tokenops_cost_auditor.services.pricing.table import PricingGapError, PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json
from tokenops_cost_auditor.services.rules.aggregate import (
    CACHE_BLIND_DISPLAY,
    CACHE_BLIND_LINE,
    CACHE_BLIND_PROVIDERS,
    INACTIVE_ON_AGGREGATE,
    UPGRADE_PATH_LINE,
    run_aggregate_detectors,
)

log = structlog.get_logger("tokenops_cost_auditor.connectors")

ACTIVE_ON_AGGREGATE = ("d1_oversized_model", "d2_missing_cache", "d3_prompt_bloat")


def active_detectors(provider: str) -> tuple[str, ...]:
    """The detectors that HONESTLY run on this provider's aggregates —
    cache-blind providers drop d2 (R-Q1: never run against fabricated zeros)."""
    if provider in CACHE_BLIND_PROVIDERS:
        return tuple(d for d in ACTIVE_ON_AGGREGATE if d != "d2_missing_cache")
    return ACTIVE_ON_AGGREGATE


def coverage_rows(provider: str = "") -> tuple[dict[str, object], ...]:
    active: tuple[dict[str, object], ...] = tuple(
        {"detector": d, "status": "active", "note": "runs on provider usage aggregates"}
        for d in active_detectors(provider)
    )
    blind: tuple[dict[str, object], ...] = (
        (
            {
                "detector": "d2_missing_cache",
                "status": "not_observable",
                "note": CACHE_BLIND_LINE.format(
                    provider=CACHE_BLIND_DISPLAY.get(provider, provider)
                ),
            },
        )
        if provider in CACHE_BLIND_PROVIDERS
        else ()
    )
    inactive: tuple[dict[str, object], ...] = tuple(
        {"detector": d, "status": "requires_per_request_logs", "note": UPGRADE_PATH_LINE}
        for d in INACTIVE_ON_AGGREGATE
    )
    return active + blind + inactive


def run_source_audit(
    session: Session,
    settings: Settings,
    table: PricingTable,
    source: Source,
    generated_at: str | None = None,
    audit: Audit | None = None,
) -> str:
    """Audit the source's accumulated usage window; returns the audit id.

    If `audit` is given (a row pre-created as 'queued' so a live progress page
    can be watched — R-LIVE-AUDIT), it is finalized to 'done' in place; else a
    fresh 'done' row is created as before (scheduled/re-audit callers)."""
    t_start = datetime.now(UTC)  # WP-PIPELINE-UI: stage stamps, same law as runner
    window_start = (datetime.now(UTC) - timedelta(days=settings.connect_backfill_days)).date()
    rows = (
        session.execute(
            select(SourceUsage)
            .where(SourceUsage.source_id == source.id, SourceUsage.day >= window_start)
            .order_by(SourceUsage.day, SourceUsage.model)
        )
        .scalars()
        .all()
    )
    frame = pd.DataFrame(
        [
            {
                "day": r.day,
                "model": r.model,
                "calls": r.calls,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cached_tokens": r.cached_tokens,
            }
            for r in rows
        ]
    )
    observed = max(int(frame["day"].nunique()), 1) if len(frame) else 1
    t_ingest = datetime.now(UTC)
    findings = (
        run_aggregate_detectors(frame, source.provider, table, settings, observed)
        if len(frame)
        else []
    )
    # Honest zeros over the detectors that actually run on aggregates.
    by_detector: dict[str, int] = {d: 0 for d in active_detectors(source.provider)}
    for f in findings:
        by_detector[f.detector] = by_detector.get(f.detector, 0) + 1
    t_detect = datetime.now(UTC)

    # As-billed spend per bucket at the verified rate card; unpriced listed.
    unpriced: set[str] = set()
    unpriced_rows = 0  # per-ROW honesty: a model unpriced one day still counts
    costs: list[float] = []  # its priced days (cold-review f.4)
    for r in rows:
        try:
            rate = table.rate(source.provider, r.model, cast(date, r.day))
        except PricingGapError:
            unpriced.add(r.model)
            unpriced_rows += 1
            costs.append(0.0)
            continue
        uncached = max(0, r.prompt_tokens - r.cached_tokens)
        costs.append(
            (
                uncached * rate.input
                + r.cached_tokens * rate.cache_read
                + r.completion_tokens * rate.output
            )
            / 1e6
        )
    total = float(sum(costs))
    t_price = datetime.now(UTC)
    monthly_spend = total * 30.0 / observed
    monthly_savings = min(sum(f.monthly_cost_impact_usd for f in findings), monthly_spend)
    total_calls = int(frame["calls"].sum()) if len(frame) else 0

    priced_pairs = [(r, c) for r, c in zip(rows, costs, strict=True) if r.model not in unpriced]
    by_model_acc: dict[str, dict[str, float]] = {}
    by_day_acc: dict[str, float] = {}
    for r, c in priced_pairs:
        m = by_model_acc.setdefault(r.model, {"calls": 0, "cost_usd": 0.0})
        m["calls"] += r.calls
        m["cost_usd"] += c
        day_key = cast(date, r.day).isoformat()
        by_day_acc[day_key] = by_day_acc.get(day_key, 0.0) + c

    if audit is None:
        audit = Audit(
            user_id=source.user_id,
            status="done",
            paid_via="subscription",
            source_id=source.id,  # R-MULTI-SOURCE: per-account attribution
        )
        session.add(audit)
    else:
        audit.status = "done"  # finalize the pre-created queued/processing row
        if audit.source_id is None:
            audit.source_id = source.id
    session.flush()

    report = ReportModel(
        audit_id=audit.id,
        observed_days=observed,
        total_spend_usd=total,
        monthly_spend_usd=monthly_spend,
        monthly_savings_usd=monthly_savings,
        monthly_optimized_usd=monthly_spend - monthly_savings,
        savings_pct=(monthly_savings / monthly_spend * 100.0) if monthly_spend > 0 else 0.0,
        spend_by_model=tuple(
            sorted(
                (
                    {"model": m, "calls": int(v["calls"]), "cost_usd": float(v["cost_usd"])}
                    for m, v in by_model_acc.items()
                ),
                key=lambda x: -float(x["cost_usd"]),  # type: ignore[arg-type]
            )
        ),
        spend_by_day=tuple({"day": d, "cost_usd": c} for d, c in sorted(by_day_acc.items())),
        findings=tuple(findings),
        unpriced_models=tuple(sorted(unpriced)),
        pricing_version=table.version,
        pricing_last_verified=(table.last_verified.isoformat() if table.last_verified else None),
        provider_mix=source.provider,
        row_count=total_calls,
        generated_at=generated_at,
        equiv_spend=False,  # T2 pulls ARE metered-API billing
        tier="account",
        coverage=coverage_rows(source.provider),
    )

    # Each scheduled run creates a NEW audit deliberately: the weekly series
    # is the dashboard's trend history (WP-2). Growth is bounded by cadence
    # (52 audits/source/year x the window's bucket rows); FR-21's "derived
    # aggregates retained" clause covers these. (G-V1 cold-reviewer f.2:
    # the previous delete-by-new-id lines were dead code and implied an
    # idempotent overwrite that was never the semantics — removed.)
    for f in findings:
        session.add(
            FindingRow(
                audit_id=audit.id,
                finding_id=f.id,
                detector=f.detector,
                route=str(f.detail.get("model")) if f.detail else None,
                severity=str(f.severity),
                monthly_impact_usd=f.monthly_cost_impact_usd,
                confidence=str(f.confidence),
                fix_text=f.fix_text,
                evidence_sample=[dataclasses.asdict(e) for e in f.evidence],
            )
        )
    for r in rows:
        session.add(
            CallAggregate(
                audit_id=audit.id,
                day=r.day,
                model=r.model,
                calls=r.calls,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                cached_tokens=r.cached_tokens,
            )
        )
    audit.row_count = total_calls
    audit.observed_days = observed
    audit.equiv_spend = False  # T2 pulls ARE metered API billing
    audit.provider_mix = source.provider
    audit.total_spend_usd = total
    audit.projected_spend_usd = report.monthly_optimized_usd
    audit.savings_pct = report.savings_pct
    audit.valid_pct = 100.0
    audit.report_ready_at = utcnow()
    source.last_audit_at = utcnow()

    # M-FLY-1 B1b: benchmark block when the cohort is honest (else absent)
    block = flywheel_benchmarks.report_block(
        session, settings, source.user_id, own_value=report.savings_pct
    )
    if block is not None:
        report = dataclasses.replace(report, benchmark=block)
    render_json(report, settings.report_dir / audit.id / "report.json")
    t_report = datetime.now(UTC)
    # A pre-created row can be re-driven after a partial failure (cold-review
    # f.1): replace, never accumulate — same FR-19 discipline as the runner.
    session.execute(delete(StageEvent).where(StageEvent.audit_id == audit.id))
    # Stage order here is the honest execution order for bucket audits:
    # detectors run on the frame BEFORE the rate-card pass (unlike the
    # upload pipeline). The /runs drawer renders by started_at, so the strip
    # tells it exactly as it ran. Counts only (FR-22).
    for stage_name, started, finished, detail in (
        (
            "ingest",
            t_start,
            t_ingest,
            {"rows": len(rows), "days": observed},
        ),
        (
            "detect",
            t_ingest,
            t_detect,
            {"detectors": by_detector, "findings": len(findings)},
        ),
        (
            "price",
            t_detect,
            t_price,
            {"priced_rows": len(rows) - unpriced_rows, "unpriced_models": sorted(unpriced)},
        ),
        ("report", t_price, t_report, {"artifacts": ["json"]}),
    ):
        session.add(
            StageEvent(
                audit_id=audit.id,
                stage=stage_name,
                started_at=started,
                finished_at=finished,
                detail=detail,
            )
        )
    log.info(
        "connector.source_audit",
        source_id=source.id,
        audit_id=audit.id,
        findings=len(findings),
        monthly_savings_usd=round(monthly_savings, 2),
    )
    return audit.id
