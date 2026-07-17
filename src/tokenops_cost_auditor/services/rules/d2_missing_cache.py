"""Detector D2 — missing prompt caching (FR-08; docs/03-LLD.md §3 + founder rulings).

Bucketing: repeated identical prefixes found via prefix_hash (confidence =
conservative), else the (provider, model, prompt_tokens) equality heuristic
(confidence = estimated). Bucket fires when count >= D2_CACHE_MIN_REPEATS,
prompt_tokens >= D2_CACHE_MIN_PROMPT_TOKENS, and the bucket shows zero caching.

Savings per founder ruling R-Q4:
    savings = reads x cacheable x (input - cache_read)
            - est_writes x cacheable x (cache_write - input)
    reads = n - est_writes; est_writes = one write per TTL window per unique
    prefix, windows counted as distinct floor(epoch / ttl_window_s) values,
    TTL per provider-family (correction C4). If windows cannot be estimated,
    est_writes = 1 and a 0.7 haircut applies to the whole estimate.

cacheable per founder ruling R-Q5:
    hash evidence -> verified prefix = min(min prompt_tokens in bucket,
    PREFIX_HASH_CHARS // 4 tokens) — the hash proves identity only over the
    hashed span. No hash -> 0.8 x min(prompt_tokens in bucket).

Monthly impact = observed savings x 30/observed_days (Q7).
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.pricing.table import PricingGapError
from tokenops_cost_auditor.services.rules.base import DetectorContext, ttl_window_s
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    make_evidence,
    monthly_factor,
    severity_for_impact,
)

CHARS_PER_TOKEN = 4  # prefix-hash char->token approximation (R-Q6 companion)


def _estimate_writes(bucket: pd.DataFrame, ttl_s: int) -> int | None:
    """Distinct TTL windows (floor(epoch/ttl)) spanned by the bucket; None when not
    estimable. Timedelta division keeps this independent of the frame's datetime
    resolution (pandas 3.0 stores datetime64[us], not [ns])."""
    ts = bucket["ts"].dropna()
    if len(ts) == 0:
        return None
    epoch = pd.Timestamp(0, tz="UTC")
    windows = ((ts - epoch) // pd.Timedelta(seconds=ttl_s)).nunique()
    return max(int(windows), 1)


class D2MissingCache:
    name = "d2_missing_cache"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        eligible = frame[
            (frame["cached_tokens"] == 0)
            & (frame["cache_write_tokens"] == 0)
            & (frame["prompt_tokens"] >= s.d2_cache_min_prompt_tokens)
        ]
        if len(eligible) == 0:
            return []

        candidates: list[tuple[pd.DataFrame, bool]] = []  # (bucket, hash_based)
        hashed = eligible[eligible["prefix_hash"].notna()]
        for _, bucket in hashed.groupby(["provider", "model", "prefix_hash"], sort=True):
            candidates.append((bucket, True))
        unhashed = eligible[eligible["prefix_hash"].isna()]
        for _, bucket in unhashed.groupby(["provider", "model", "prompt_tokens"], sort=True):
            candidates.append((bucket, False))

        results: list[tuple[float, bool, pd.DataFrame, str]] = []
        for bucket, hash_based in candidates:
            n = len(bucket)
            if n < s.d2_cache_min_repeats:
                continue
            provider = str(bucket["provider"].iloc[0])
            model = str(bucket["model"].iloc[0])
            min_prompt = int(bucket["prompt_tokens"].min())
            cacheable: float
            if hash_based:
                cacheable = float(min(min_prompt, s.prefix_hash_chars // CHARS_PER_TOKEN))
            else:
                cacheable = s.d2_suffix_haircut * min_prompt  # R-Q5: 0.8 x min

            try:
                rate = ctx.table.rate(provider, model, bucket["ts"].iloc[0].date())
            except PricingGapError:
                continue  # unpriced model: cost impact unknowable; skip bucket

            ttl = ttl_window_s(s, provider, model)
            est_writes = _estimate_writes(bucket, ttl)
            haircut = 1.0
            if est_writes is None:
                est_writes = 1  # R-Q4 fallback: one write, 0.7 haircut on estimate
                haircut = s.d2_no_window_haircut
            reads = n - est_writes
            if reads <= 0:
                continue
            gross = reads * cacheable * (rate.input - rate.cache_read) / 1e6
            penalty = est_writes * cacheable * (rate.cache_write - rate.input) / 1e6
            savings_obs = (gross - penalty) * haircut
            if savings_obs <= 0:
                continue
            results.append((savings_obs, hash_based, bucket, model))

        results.sort(key=lambda r: -r[0])
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        for i, (savings_obs, hash_based, bucket, model) in enumerate(results, start=1):
            monthly = savings_obs * factor
            findings.append(
                Finding(
                    id=f"D2-{i:03d}",
                    detector=self.name,
                    severity=severity_for_impact(monthly),
                    monthly_cost_impact_usd=monthly,
                    confidence=Confidence.CONSERVATIVE if hash_based else Confidence.ESTIMATED,
                    fix_text=(
                        f"Enable prompt caching for the repeated prefix on {model} "
                        f"({len(bucket)} uncached calls with an identical prefix "
                        f"{'(hash-verified)' if hash_based else '(size-matched estimate)'}). "
                        "Mark the shared system/context prefix as cacheable in your API "
                        "calls; the varying suffix stays uncached."
                    ),
                    evidence=make_evidence(bucket, note="uncached repeated-prefix call"),
                )
            )
        return findings
