"""Detector D6 — chatty loops / batchable agent bursts (FR-12; docs/03-LLD.md §3).

Session = same tag, split at gaps > D6_SESSION_GAP_S (15 min). Within a session,
a RUN collects consecutive small calls (completion < D6_SMALL_COMPLETION_T)
whose span stays within D6_RUN_WINDOW_S of the run start (anchor rule, like D4).
A run of >= D6_LOOP_MIN calls is batchable. Agent re-read signature: any
prefix_hash occurring >= D6_REREAD_MIN times within the session — flagged as
"agent loop suspected" in the finding text.

Aggregation (R-D6-AGG, founder 2026-07-18): ONE finding per session — monthly
impact summed over the session's qualifying runs, run count in the finding
text, evidence sampled across runs (<=20), per-run breakdown carried in
Finding.detail (report.json only). Dogfood context: per-run findings produced
856 D6 rows on 13 real sessions.

Savings (LLD: batchable x overhead x rate; overhead defined as a documented
money-math default, see pricing_golden_NOTES.md):
    saved_calls = n - ceil(n / D6_BATCH_SZ)
    overhead_tokens = median prompt_tokens of the run (per-call context re-send)
    savings = saved_calls x overhead_tokens x effective_prompt_rate / 1e6
    (effective = as billed: cache reads at cache_read rate — UAT-1 fix, D11)
Confidence = estimated. Monthly impact = observed x 30/observed_days (Q7).
"""

from __future__ import annotations

import math

import pandas as pd

from tokenops_cost_auditor.services.pricing.table import PricingGapError
from tokenops_cost_auditor.services.rules.base import DetectorContext, split_on_gap
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    effective_prompt_rate,
    monthly_factor,
    route_label,
    sample_evidence_across,
    severity_for_impact,
)


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

        # R-D6-AGG: one result per SESSION (impact summed over qualifying runs)
        results: list[tuple[float, list[pd.DataFrame], list[dict[str, object]], str, bool]] = []
        for tag, group in frame.groupby("tag", sort=True):
            for session in split_on_gap(group, s.d6_session_gap_s):
                hash_counts = session["prefix_hash"].dropna().value_counts()
                reread = bool((hash_counts >= s.d6_reread_min).any())
                session_savings = 0.0
                session_runs: list[pd.DataFrame] = []
                run_details: list[dict[str, object]] = []
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
                        # every saved call is priced at the run's MINIMUM
                        # EFFECTIVE prompt rate (G3 cold-reviewer f.3; UAT-1
                        # dogfood fix — cache-read-heavy agent context re-sends
                        # were priced at flat input rate, ~10x over-claim);
                        # uncached single-model runs reduce to saved x overhead
                        # x input rate exactly
                        min_rate = min(
                            effective_prompt_rate(
                                r,
                                ctx.table.rate(str(r["provider"]), str(r["model"]), r["ts"].date()),
                            )
                            for _, r in run.iterrows()
                        )
                    except PricingGapError:
                        continue  # unpriced model: impact unknowable; skip run
                    savings_obs = saved_calls * overhead * min_rate / 1e6
                    if savings_obs <= 0:
                        continue
                    session_savings += savings_obs
                    session_runs.append(run)
                    run_details.append(
                        {
                            "start_ts": run["ts"].min().isoformat(),
                            "calls": n,
                            "saved_calls": saved_calls,
                            "observed_savings_usd": savings_obs,
                        }
                    )
                if session_savings <= 0:
                    continue
                results.append((session_savings, session_runs, run_details, str(tag), reread))

        results.sort(key=lambda r: -r[0])
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        for i, (session_savings, session_runs, run_details, tag, reread) in enumerate(
            results, start=1
        ):
            monthly = session_savings * factor
            n_calls = sum(len(r) for r in session_runs)
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
                        f"{loop_note}Tag '{tag}' issued {len(session_runs)} burst(s) of "
                        f"small sequential calls in one session ({n_calls} calls total) "
                        "that are batchable. Combine related items into one request "
                        f"(batches of ~{ctx.settings.d6_batch_sz}) so shared context is "
                        "sent once instead of per call; savings assume only the re-sent "
                        "context (run-median prompt size) is eliminated."
                    ),
                    evidence=sample_evidence_across(
                        session_runs, note="small sequential call in burst"
                    ),
                    detail={"route": route_label(tag), "runs": run_details},
                )
            )
        return findings
