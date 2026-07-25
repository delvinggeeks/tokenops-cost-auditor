"""Detector D9 — ineffective caching (founder 2026-07-25, "richer findings").

Where prompt caching IS set up (cache_write_tokens > 0) but the reads don't pay
it back: you keep paying the cache-WRITE premium while earning little cache-READ
discount, so the caching NET COSTS you money. Disjoint from D2 by construction —
D2 only considers rows with cache_write_tokens == 0 (no caching at all), so no ROW
is counted by both and the DOLLARS never double-count. (The same route can still
surface in both a D2 and a D9 finding when it mixes never-cached and cache-written
calls — the savings amounts never overlap.)

Money math (from the ACTUAL billed cache_write / cache_read token counts, so
CONSERVATIVE — not an estimate; R-Q4 rate roles):

    net_loss = Σ (cache_write - input) x cache_write_tokens   # write premium PAID
             - Σ (input - cache_read) x cached_tokens         # read discount EARNED

    per (provider, model, route); flagged when net_loss > 0 (caching costs more
    than it saves) over at least D9_MIN_CACHE_WRITE_TOKENS. Rates are per-1M and
    per-row date-priced (a bucket can span a pricing effective-date boundary).
    Monthly impact = net_loss x 30/observed_days (Q7). Models with no write
    premium (cache_write defaults to input) can never net-lose, so are silent.

Per-request only (aggregates carry no cache_write count): INACTIVE_ON_AGGREGATE.
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.pricing.table import PricingGapError
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    make_evidence,
    monthly_factor,
    severity_for_impact,
)


class D9IneffectiveCache:
    name = "d9_ineffective_cache"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        active = frame[frame["cache_write_tokens"] > 0]
        if len(active) == 0:
            return []

        results: list[tuple[float, str, str, pd.DataFrame]] = []
        for (provider, model, tag), bucket in active.groupby(
            ["provider", "model", "tag"], sort=True
        ):
            if int(bucket["cache_write_tokens"].sum()) < s.d9_min_cache_write_tokens:
                continue
            loss_obs = 0.0
            try:
                for _, row in bucket.sort_values("ts").iterrows():
                    rate = ctx.table.rate(str(provider), str(model), row["ts"].date())
                    cw = int(row["cache_write_tokens"])
                    cr = int(row["cached_tokens"])
                    loss_obs += (rate.cache_write - rate.input) * cw / 1e6  # write premium
                    loss_obs -= (rate.input - rate.cache_read) * cr / 1e6  # read discount
            except PricingGapError:
                # An unpriced model OR a partial pricing-date gap in the bucket
                # (some rows before a model's first effective_from) makes the loss
                # unknowable → skip the WHOLE bucket rather than invent a number.
                # Same conservative choice as D2 (d2_missing_cache.py).
                continue
            if loss_obs <= 0:
                continue  # caching is net-positive here: working fine, not flagged
            results.append((loss_obs, str(model), str(tag), bucket))

        results.sort(key=lambda r: -r[0])
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        for i, (loss_obs, model, tag, bucket) in enumerate(results, start=1):
            monthly = loss_obs * factor
            findings.append(
                Finding(
                    id=f"D9-{i:03d}",
                    detector=self.name,
                    severity=severity_for_impact(monthly),
                    monthly_cost_impact_usd=monthly,
                    # arithmetic on OBSERVED billed tokens — not a heuristic estimate
                    confidence=Confidence.CONSERVATIVE,
                    fix_text=(
                        f"Prompt caching on route '{tag}' ({model}) is costing more than it "
                        "saves — you pay the cache-write premium but the cache is rarely read "
                        "back. Make the cached prefix stable and reuse it within the cache TTL, "
                        "or stop caching this route. Reclaims about "
                        f"${monthly:,.2f}/month at the observed read rate."
                    ),
                    evidence=make_evidence(bucket, note="cache written but rarely read"),
                )
            )
        return findings
