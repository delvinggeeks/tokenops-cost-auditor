"""Detector D6 — chatty loops / batchable agent bursts (FR-12; docs/03-LLD.md §3).

Session = same tag, split at gaps > D6_SESSION_GAP_S (15 min). Within a session,
a RUN collects consecutive small calls (completion < D6_SMALL_COMPLETION_T)
whose span stays within D6_RUN_WINDOW_S of the run start (anchor rule, like D4).
A run of >= D6_LOOP_MIN calls is batchable. Agent re-read signature: any
prefix_hash occurring >= D6_REREAD_MIN times within the session — flagged as
"agent loop suspected" in the finding text.

Savings (LLD: batchable x overhead x rate; overhead defined as a documented
money-math default, see pricing_golden_NOTES.md):
    saved_calls = n - ceil(n / D6_BATCH_SZ)
    overhead_tokens = median prompt_tokens of the run (per-call context re-send)
    savings = saved_calls x overhead_tokens x input_rate / 1e6
Confidence = estimated. Monthly impact = observed x 30/observed_days (Q7).
"""

from __future__ import annotations

import math

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


def _split_on_gap(group: pd.DataFrame, gap_s: int) -> list[pd.DataFrame]:
    ordered = group.sort_values("ts")
    out: list[pd.DataFrame] = []
    start = 0
    times = ordered["ts"].tolist()
    for i in range(1, len(times) + 1):
        if i == len(times) or (times[i] - times[i - 1]).total_seconds() > gap_s:
            out.append(ordered.iloc[start:i])
            start = i
    return out


def _runs(session: pd.DataFrame, small_t: int, window_s: int) -> list[pd.DataFrame]:
    small = session[session["completion_tokens"] < small_t].sort_values("ts")
    out: list[pd.DataFrame] = []
    start = 0
    times = small["ts"].tolist()
    for i in range(1, len(times) + 1):
        if i == len(times) or (times[i] - times[start]).total_seconds() > window_s:
            out.append(small.iloc[start:i])
            start = i
    return out


class D6ChattyLoop:
    name = "d6_chatty_loop"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []

        results: list[tuple[float, pd.DataFrame, str, bool, int]] = []
        for tag, group in frame.groupby("tag", sort=True):
            for session in _split_on_gap(group, s.d6_session_gap_s):
                hash_counts = session["prefix_hash"].dropna().value_counts()
                reread = bool((hash_counts >= s.d6_reread_min).any())
                for run in _runs(session, s.d6_small_completion_t, s.d6_run_window_s):
                    n = len(run)
                    if n < s.d6_loop_min:
                        continue
                    saved_calls = n - math.ceil(n / s.d6_batch_sz)
                    if saved_calls <= 0:
                        continue
                    overhead = float(run["prompt_tokens"].quantile(0.5))
                    try:
                        # order-independent and conservative for mixed-model runs:
                        # every saved call is priced at the run's MINIMUM input
                        # rate (G3 cold-reviewer f.3); single-model runs reduce
                        # to saved x overhead x rate exactly
                        min_rate = min(
                            ctx.table.rate(
                                str(r["provider"]), str(r["model"]), r["ts"].date()
                            ).input
                            for _, r in run.iterrows()
                        )
                    except PricingGapError:
                        continue  # unpriced model: impact unknowable; skip run
                    savings_obs = saved_calls * overhead * min_rate / 1e6
                    if savings_obs <= 0:
                        continue
                    results.append((savings_obs, run, str(tag), reread, n))

        results.sort(key=lambda r: -r[0])
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        for i, (savings_obs, run, tag, reread, n) in enumerate(results, start=1):
            monthly = savings_obs * factor
            loop_note = (
                "Agent loop suspected: the same prompt prefix recurs repeatedly in "
                "this session (context re-read signature). "
                if reread
                else ""
            )
            findings.append(
                Finding(
                    id=f"D6-{i:03d}",
                    detector=self.name,
                    severity=severity_for_impact(monthly),
                    monthly_cost_impact_usd=monthly,
                    confidence=Confidence.ESTIMATED,
                    fix_text=(
                        f"{loop_note}Tag '{tag}' issued a burst of {n} small sequential "
                        "calls that are batchable. Combine related items into one "
                        f"request (batches of ~{ctx.settings.d6_batch_sz}) so shared "
                        "context is sent once instead of per call; savings assume only "
                        "the re-sent context (run-median prompt size) is eliminated."
                    ),
                    evidence=make_evidence(run, note="small sequential call in burst"),
                )
            )
        return findings
