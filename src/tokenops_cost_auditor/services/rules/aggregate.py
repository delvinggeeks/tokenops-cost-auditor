"""T2 ACCOUNT-tier reduced detector set (PLAN-V15 §0 R-Q1; docs/12 Stage 1).

Pure math over aggregate usage buckets (day x model): no I/O, no network —
inside the engine boundary, T-NFR-01 applies. ACTIVE on aggregates: D1
(model-mix vs avg completion size per bucket), D2 (provider cached-token
fields), D3 (prompt-size averages, coarse). D4/D5/D6 CANNOT run on
aggregates: the report layer renders them as labeled "requires per-request
logs" rows via INACTIVE_ON_AGGREGATE — no savings number is ever emitted
for them here (R-Q1 law). All aggregate findings carry
confidence=ESTIMATED.

Unpriced models (PricingGapError) are skipped conservatively and WITHOUT
logging — this module stays pure (no I/O). Any usage model skipped here is
also unpriced in the caller's spend pass and therefore surfaces in
report.unpriced_models (FR-28); the one silent corner is an unpriced d1
DOWNGRADE TARGET, which skips the finding entirely (never invent a number)
— noted in source_audit.py's docstring. (G-V1 cold-reviewer f.3.)

Money math: each estimator has a hand-derived golden in
tests/test_aggregate_rules.py against tests/fixtures/aggregate_usage.json,
with the spreadsheet derivation in tests/fixtures/pricing_golden_NOTES.md
(CLAUDE.md rule 4).

Expected frame columns: day (date), model (str), calls (int),
prompt_tokens, completion_tokens, cached_tokens (ints).
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.pricing.table import (
    PricingGapError,
    PricingTable,
    Rate,
)
from tokenops_cost_auditor.services.rules.d1_oversized_model import _frontier_match
from tokenops_cost_auditor.services.rules.findings import (
    SEVERITY_HIGH_USD,
    SEVERITY_MED_USD,
    Confidence,
    EvidenceRef,
    Finding,
    Severity,
)

INACTIVE_ON_AGGREGATE: tuple[str, ...] = (
    "d4_retry_storm",
    "d5_unbounded_max_tokens",
    "d6_chatty_loop",
    "d8_spend_concentration",  # needs per-request route tags
    "d9_ineffective_cache",  # aggregates carry no cache_write count
    "d10_spend_anomaly",  # needs per-request daily spend (aggregate prices buckets itself)
)
UPGRADE_PATH_LINE = (
    "Requires per-request logs — upload a JSONL export or run the collector "
    "to enable this detector."
)
# WP-CLOUD-T2 C-A (R-Q1 honesty): Azure Monitor exposes no cached-token
# COUNT for standard deployments, so cached_tokens is 0 by construction in
# azure buckets. Running the cache detector against that fabricated zero
# would flag "missing cache" at customers who cache heavily — d2 is
# NOT OBSERVABLE there, and says so, rather than guessing.
CACHE_BLIND_PROVIDERS: tuple[str, ...] = ("azure-openai", "vertex-ai")
CACHE_BLIND_LINE = (
    "Not observable on {provider} — the provider's usage metric splits "
    "input/output only, not cached tokens. Upload a JSONL export to enable "
    "this detector."
)
CACHE_BLIND_DISPLAY = {"azure-openai": "Azure", "vertex-ai": "Vertex"}

MONTH_DAYS = 30.0


def _severity(monthly_usd: float) -> Severity:
    if monthly_usd >= SEVERITY_HIGH_USD:
        return Severity.HIGH
    if monthly_usd >= SEVERITY_MED_USD:
        return Severity.MED
    return Severity.LOW


def _bucket_cost(rate: Rate, prompt: float, cached: float, completion: float) -> float:
    """As-billed bucket cost, USD: uncached prompt at input, cached at
    cache_read, completion at output. Cache WRITES are unobservable in
    aggregates — omitting them UNDERSTATES both costs; for D1 the delta
    direction is conservative (both models priced identically without
    writes)."""
    uncached = max(0.0, prompt - cached)
    return (uncached * rate.input + cached * rate.cache_read + completion * rate.output) / 1e6


def _evidence(rows: pd.DataFrame, note: str) -> tuple[EvidenceRef, ...]:
    out = []
    for idx, row in rows.head(20).iterrows():
        out.append(
            EvidenceRef(
                row_idx=int(idx),
                ts=str(row["day"]),
                model=str(row["model"]),
                tokens=int(row["prompt_tokens"] + row["completion_tokens"]),
                note=note,
            )
        )
    return tuple(out)


def d1_aggregate(
    frame: pd.DataFrame,
    provider: str,
    table: PricingTable,
    settings: Settings,
    observed_days: int,
) -> list[Finding]:
    """Oversized model, aggregate variant: a mapped frontier model whose
    average completion per call (over the window) is below
    D1_SHORT_COMPLETION_T is repriced bucket-by-bucket at its downgrade
    target; savings = cost(current) - cost(target), scaled to monthly."""
    findings: list[Finding] = []
    scale = MONTH_DAYS / max(observed_days, 1)
    map_keys = list(settings.d1_model_map)
    for n, (model, rows) in enumerate(frame.groupby("model", sort=True), start=1):
        key = _frontier_match(str(model).lower(), map_keys)
        if key is None:
            continue
        target = settings.d1_model_map[key]
        calls = int(rows["calls"].sum())
        if calls == 0:
            continue
        avg_completion = float(rows["completion_tokens"].sum()) / calls
        if avg_completion >= settings.d1_short_completion_t:
            continue
        try:
            current = sum(
                _bucket_cost(
                    table.rate(provider, str(model), r["day"]),
                    r["prompt_tokens"],
                    r["cached_tokens"],
                    r["completion_tokens"],
                )
                for _, r in rows.iterrows()
            )
            alt = sum(
                _bucket_cost(
                    table.rate(provider, target, r["day"]),
                    r["prompt_tokens"],
                    r["cached_tokens"],
                    r["completion_tokens"],
                )
                for _, r in rows.iterrows()
            )
        except PricingGapError:
            continue  # unpriced model/target: never invent a number
        monthly = max(0.0, current - alt) * scale
        if monthly <= 0:
            continue
        findings.append(
            Finding(
                id=f"D1A-{n:03d}",
                detector="d1_oversized_model",
                severity=_severity(monthly),
                monthly_cost_impact_usd=monthly,
                confidence=Confidence.ESTIMATED,
                fix_text=(
                    f"Average completion is {avg_completion:.0f} tokens per call on "
                    f"{model}; route this traffic to {target} and keep the frontier "
                    "model for genuinely long generations."
                ),
                evidence=_evidence(rows, "aggregate-bucket"),
                detail={"model": str(model), "target": target, "avg_completion": avg_completion},
            )
        )
    return findings


def d2_aggregate(
    frame: pd.DataFrame,
    provider: str,
    table: PricingTable,
    settings: Settings,
    observed_days: int,
) -> list[Finding]:
    """Missing cache, aggregate variant: uses ONLY the provider-reported
    cached-token fields. Target cache share per model = the account's own
    best observed bucket share (never an invented benchmark); buckets below
    target are priced as if lifted to it, haircut by D2_SUFFIX_HAIRCUT."""
    findings: list[Finding] = []
    scale = MONTH_DAYS / max(observed_days, 1)
    for n, (model, rows) in enumerate(frame.groupby("model", sort=True), start=1):
        priced = rows[rows["prompt_tokens"] > 0]
        if priced.empty:
            continue
        shares = priced["cached_tokens"] / priced["prompt_tokens"]
        target_share = float(shares.max())
        if target_share <= 0:
            continue  # account shows no caching on this model: nothing observed to extend
        savings = 0.0
        for _, r in priced.iterrows():
            extra = max(0.0, target_share * r["prompt_tokens"] - r["cached_tokens"])
            if extra <= 0:
                continue
            try:
                rate = table.rate(provider, str(model), r["day"])
            except PricingGapError:
                continue
            savings += extra * (rate.input - rate.cache_read) / 1e6
        monthly = savings * settings.d2_suffix_haircut * scale
        if monthly <= 0:
            continue
        findings.append(
            Finding(
                id=f"D2A-{n:03d}",
                detector="d2_missing_cache",
                severity=_severity(monthly),
                monthly_cost_impact_usd=monthly,
                confidence=Confidence.ESTIMATED,
                fix_text=(
                    f"Your best day on {model} cached {target_share:.0%} of prompt "
                    "tokens; other days fall short of your own demonstrated ceiling. "
                    "Make the cached prefix consistent across deploys."
                ),
                evidence=_evidence(priced, "aggregate-bucket"),
                detail={"model": str(model), "target_share": target_share},
            )
        )
    return findings


def d3_aggregate(
    frame: pd.DataFrame,
    provider: str,
    table: PricingTable,
    settings: Settings,
    observed_days: int,
) -> list[Finding]:
    """Prompt bloat, aggregate variant (coarse): per model, buckets whose
    average prompt size exceeds D3_BLOAT_MULT x the model's median bucket
    average are charged for the excess at the bucket's as-billed effective
    prompt rate. Needs >= 3 buckets for a meaningful median."""
    findings: list[Finding] = []
    scale = MONTH_DAYS / max(observed_days, 1)
    for n, (model, rows) in enumerate(frame.groupby("model", sort=True), start=1):
        priced = rows[rows["calls"] > 0]
        if len(priced) < 3:
            continue
        avgs = priced["prompt_tokens"] / priced["calls"]
        baseline = float(avgs.median())
        if baseline <= 0:
            continue
        savings = 0.0
        bloated = 0
        for (_, r), avg in zip(priced.iterrows(), avgs, strict=True):
            if avg <= settings.d3_bloat_mult * baseline or r["prompt_tokens"] <= 0:
                continue
            try:
                rate = table.rate(provider, str(model), r["day"])
            except PricingGapError:
                continue
            uncached = max(0.0, r["prompt_tokens"] - r["cached_tokens"])
            eff_rate = (uncached * rate.input + r["cached_tokens"] * rate.cache_read) / r[
                "prompt_tokens"
            ]
            savings += (avg - baseline) * r["calls"] * eff_rate / 1e6
            bloated += 1
        monthly = savings * scale
        if monthly <= 0:
            continue
        findings.append(
            Finding(
                id=f"D3A-{n:03d}",
                detector="d3_prompt_bloat",
                severity=_severity(monthly),
                monthly_cost_impact_usd=monthly,
                confidence=Confidence.ESTIMATED,
                fix_text=(
                    f"{bloated} day-bucket(s) on {model} average more than "
                    f"{settings.d3_bloat_mult:.0f}x the model's median prompt size; "
                    "trim system-prompt or context growth on those routes."
                ),
                evidence=_evidence(priced, "aggregate-bucket"),
                detail={"model": str(model), "baseline_avg_prompt": baseline},
            )
        )
    return findings


def run_aggregate_detectors(
    frame: pd.DataFrame,
    provider: str,
    table: PricingTable,
    settings: Settings,
    observed_days: int,
) -> list[Finding]:
    findings = (
        d1_aggregate(frame, provider, table, settings, observed_days)
        + (
            d2_aggregate(frame, provider, table, settings, observed_days)
            if provider not in CACHE_BLIND_PROVIDERS
            else []  # cache counts are fabricated zeros there — see CACHE_BLIND_LINE
        )
        + d3_aggregate(frame, provider, table, settings, observed_days)
    )
    return sorted(findings, key=lambda f: f.monthly_cost_impact_usd, reverse=True)
