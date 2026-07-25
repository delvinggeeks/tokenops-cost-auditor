"""Detector D1 — oversized model for the task (FR-07; docs/03-LLD.md §3 + R-D1-MAP).

Buckets: (tag, endpoint, provider, model) for frontier models — frontier = the
R-D1-MAP downgrade-map keys plus D1_FRONTIER_MODELS extras (longest-prefix match
on model id). Candidate when the bucket's completion p50 < D1_SHORT_COMPLETION_T
AND the bucket shows no cache usage ("no cached reasoning marker" — documented
interpretation: cached buckets are excluded, which only ever REDUCES findings).

Savings (R-D1-MAP c): re-price every bucket row at the suggested model's
four-rate card and take the difference — algebraically identical to the LLD's
"calls x rate delta applied to token means" because the cost formula is linear.
Exactly ONE tier down, never cross-provider (a/b). Confidence = estimated.
Every finding carries the R-D1-MAP(e) caveat verbatim. Frontier models without
a mapped downgrade, or with an unpriced card on either side, produce an
INFORMATIONAL finding with no savings number (f).
Monthly impact = observed savings x 30/observed_days (Q7).
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.pricing.table import PricingGapError, PricingTable
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    Severity,
    make_evidence,
    monthly_factor,
    severity_for_impact,
)

QUALITY_CAVEAT = "model suitability requires your own quality evaluation"  # R-D1-MAP(e)


def _frontier_match(model: str, keys: list[str]) -> str | None:
    """Exact key, or key + dated-snapshot suffix ('-2...'), longest key wins.
    The boundary rule stops sibling bleed: gpt-5.4-nano must NOT match 'gpt-5.4',
    while claude-opus-4-20250514 DOES match 'claude-opus-4'."""
    model = model.lower()
    candidates = [k for k in keys if model == k.lower() or model.startswith(k.lower() + "-2")]
    return max(candidates, key=len) if candidates else None


def _repriced_cost(bucket: pd.DataFrame, table: PricingTable, provider: str, model: str) -> float:
    """Sum of bucket costs at `model`'s four-rate card (per-row date lookup)."""
    total = 0.0
    for _, row in bucket.iterrows():
        rate = table.rate(provider, model, row["ts"].date())
        uncached = max(
            int(row["prompt_tokens"]) - int(row["cached_tokens"]) - int(row["cache_write_tokens"]),
            0,
        )
        total += (
            uncached * rate.input
            + int(row["cached_tokens"]) * rate.cache_read
            + int(row["cache_write_tokens"]) * rate.cache_write
            + int(row["completion_tokens"]) * rate.output
        ) / 1e6
    return total


class D1OversizedModel:
    name = "d1_oversized_model"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        map_keys = list(s.d1_model_map.keys())
        frontier_keys = map_keys + list(s.d1_frontier_models)

        priced_results: list[tuple[float, pd.DataFrame, str, str]] = []
        informational: list[tuple[pd.DataFrame, str]] = []
        for (_tag, _endpoint, provider, model), bucket in frame.groupby(
            ["tag", "endpoint", "provider", "model"], sort=True
        ):
            if _frontier_match(str(model), frontier_keys) is None:
                continue
            if float(bucket["completion_tokens"].quantile(0.5)) >= s.d1_short_completion_t:
                continue
            has_cache_use = (
                int(bucket["cached_tokens"].sum()) > 0
                or int(bucket["cache_write_tokens"].sum()) > 0
            )
            if has_cache_use:
                continue  # cached reasoning marker: excluded (conservative)

            map_key = _frontier_match(str(model), map_keys)
            if map_key is None:
                informational.append((bucket, str(model)))  # R-D1-MAP(f): no map entry
                continue
            suggested = s.d1_model_map[map_key]
            try:
                current_cost = float(bucket["cost_usd"].sum())
                if bucket["cost_usd"].isna().any():
                    raise PricingGapError(str(provider), str(model), bucket["ts"].iloc[0].date())
                suggested_cost = _repriced_cost(bucket, ctx.table, str(provider), suggested)
            except PricingGapError:
                informational.append((bucket, str(model)))  # unpriced card on either side
                continue
            savings_obs = current_cost - suggested_cost
            if savings_obs <= 0:
                continue
            priced_results.append((savings_obs, bucket, str(model), suggested))

        priced_results.sort(key=lambda r: -r[0])
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        for i, (savings_obs, bucket, model, suggested) in enumerate(priced_results, start=1):
            monthly = savings_obs * factor
            findings.append(
                Finding(
                    id=f"D1-{i:03d}",
                    detector=self.name,
                    severity=severity_for_impact(monthly),
                    monthly_cost_impact_usd=monthly,
                    confidence=Confidence.ESTIMATED,  # R-D1-MAP(c)
                    fix_text=(
                        f"Route this workload from {model} to {suggested}: "
                        f"{len(bucket)} calls with median completion under "
                        f"{s.d1_short_completion_t} tokens fit a smaller model's "
                        f"response profile. Savings are computed at {suggested}'s "
                        f"published rates; {QUALITY_CAVEAT}."
                    ),
                    evidence=make_evidence(bucket, note="short-completion frontier call"),
                    detail={"route": model},
                )
            )
        for j, (bucket, model) in enumerate(informational, start=1):
            findings.append(
                Finding(
                    id=f"D1-INFO-{j:03d}",
                    detector=self.name,
                    severity=Severity.LOW,
                    monthly_cost_impact_usd=0.0,
                    confidence=Confidence.ESTIMATED,
                    fix_text=(
                        f"{len(bucket)} short-completion calls on frontier model {model} "
                        "have no ruled downgrade mapping or no published rate card, so no "
                        f"savings figure is stated. Review this route manually; {QUALITY_CAVEAT}."
                    ),
                    evidence=make_evidence(bucket, note="short-completion frontier call"),
                )
            )
        return findings
