"""Detector D3 — prompt bloat (FR-09; docs/03-LLD.md §3 + accepted default Q10).

Corpus norm: rows are binned by floor(log2(completion_tokens)) ("similar
completion sizes", Q10); the corpus median prompt_tokens is computed per bin
over the WHOLE frame. A route subgroup (tag, endpoint) x bin is flagged when
its prompt p90 > D3_BLOAT_MULT x corpus median of that bin.

Savings (documented money-math default, see pricing_golden_NOTES.md):
    excess = sum over flagged rows of max(prompt_i - corpus_median(bin), 0)
    savings = excess x effective_prompt_rate(call) x 0.5 safety factor
    (effective = as billed: cache reads at cache_read rate — UAT-1 fix, D11;
    uncached rows reduce to the LLD §3 input-rate formula exactly)
Confidence = estimated (statistical norm, not verified content).
Monthly impact = observed savings x 30/observed_days (Q7).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tokenops_cost_auditor.services.pricing.table import PricingGapError
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    effective_prompt_rate,
    make_evidence,
    monthly_factor,
    route_label,
    severity_for_impact,
)

SAFETY_FACTOR = 0.5  # LLD §3: savings = excess x input_rate x 0.5


def _completion_bin(completion: pd.Series) -> pd.Series:
    return np.floor(np.log2(completion.clip(lower=1))).astype(int)


class D3PromptBloat:
    name = "d3_prompt_bloat"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        work = frame.copy()
        work["_bin"] = _completion_bin(work["completion_tokens"])
        corpus_median = work.groupby("_bin")["prompt_tokens"].median()

        results: list[tuple[float, pd.DataFrame, str, str]] = []
        for (tag, endpoint, bin_id), sub in work.groupby(["tag", "endpoint", "_bin"], sort=True):
            median = float(corpus_median[bin_id])
            if median <= 0:
                continue
            p90 = float(sub["prompt_tokens"].quantile(0.9))
            if p90 <= s.d3_bloat_mult * median:
                continue
            savings_obs = 0.0
            try:
                for _, row in sub.iterrows():
                    excess = max(int(row["prompt_tokens"]) - median, 0.0)
                    if excess <= 0:
                        continue
                    rate = ctx.table.rate(str(row["provider"]), str(row["model"]), row["ts"].date())
                    # tokens are priced as the row was billed (cache reads at the
                    # read rate) — flat input-rate pricing inflated cache-heavy
                    # agent traffic ~10x (UAT-1 dogfood fix, D11)
                    savings_obs += excess * effective_prompt_rate(row, rate) * SAFETY_FACTOR / 1e6
            except PricingGapError:
                continue  # unpriced model in route: impact unknowable; skip
            if savings_obs <= 0:
                continue
            results.append((savings_obs, sub, str(tag), str(endpoint)))

        results.sort(key=lambda r: -r[0])
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        for i, (savings_obs, sub, tag, endpoint) in enumerate(results, start=1):
            monthly = savings_obs * factor
            findings.append(
                Finding(
                    id=f"D3-{i:03d}",
                    detector=self.name,
                    severity=severity_for_impact(monthly),
                    monthly_cost_impact_usd=monthly,
                    confidence=Confidence.ESTIMATED,
                    fix_text=(
                        f"Route '{tag}' {endpoint or '(no endpoint)'} sends prompts far "
                        "larger than comparable traffic producing similar-length "
                        f"responses (p90 {int(sub['prompt_tokens'].quantile(0.9))} tokens "
                        "vs corpus norm). Trim static instructions, deduplicate context, "
                        "and move stable content behind prompt caching. Savings assume "
                        "only half the excess is removable (0.5 safety factor)."
                    ),
                    evidence=make_evidence(sub, note="prompt above corpus norm"),
                    detail={"route": route_label(tag), "endpoint": endpoint},
                )
            )
        return findings
