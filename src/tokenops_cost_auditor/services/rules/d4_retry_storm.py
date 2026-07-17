"""Detector D4 — retry storms / duplicate calls (FR-10; docs/03-LLD.md §3).

Eligibility (UAT-1 dogfood fix, D11): rows with ANY cache activity are
excluded. A call that reads or writes provider cache is a session
continuation, not a blind duplicate — cache-stable agent sessions repeat
token shapes every few seconds, and treating those steps as retry storms was
a false-positive factory on real Claude Code traffic. A true duplicate of a
cached call also pays cache-read rates, so full-cost "waste" would be
overstated anyway.

Near-identical identity key: (tag, model, prefix_hash) when a hash exists
(confidence = conservative), else (tag, model, prompt_tokens,
completion_tokens) (= estimated; prompt-only collided massively on agent
traffic). Within each identity group (time-sorted), a cluster collects calls whose ts is
within D4_WINDOW_S of the CLUSTER START (anchor rule — deterministic). A cluster
of >= D4_DUP_MIN near-identical calls is a storm: wasted = (n-1) x mean cost of
the cluster's priced rows.

Aggregation (R-D6-AGG, founder 2026-07-18 — identical to D6): ONE finding per
SESSION (same tag, split at gaps > D6_SESSION_GAP_S), waste summed over every
storm cluster in the session, cluster count in the finding text, evidence
sampled across clusters (<=20), per-cluster breakdown in Finding.detail
(report.json only). Severity HIGH if any cluster >= 10 (LLD rule), else MED.
Monthly impact = observed waste x 30/observed_days (Q7).
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.rules.base import DetectorContext, split_on_gap
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    Severity,
    monthly_factor,
    sample_evidence_across,
)

HIGH_SEVERITY_CLUSTER = 10  # LLD §3: high severity if any window >= 10


def _clusters(group: pd.DataFrame, window_s: int) -> list[pd.DataFrame]:
    ordered = group.sort_values("ts")
    out: list[pd.DataFrame] = []
    start_idx = 0
    times = ordered["ts"].tolist()
    for i in range(1, len(times) + 1):
        if i == len(times) or (times[i] - times[start_idx]).total_seconds() > window_s:
            out.append(ordered.iloc[start_idx:i])
            start_idx = i
    return out


class D4RetryStorm:
    name = "d4_retry_storm"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        work = frame[(frame["cached_tokens"] == 0) & (frame["cache_write_tokens"] == 0)].copy()
        # UAT-D5: rows sharing a request_id are the SAME call (logger echoes,
        # streaming events), never a retry — duplicates must not form clusters
        work = work.drop_duplicates(subset=["request_id"], keep="first")
        if len(work) == 0:
            return []
        work["_identity"] = work["prefix_hash"].where(
            work["prefix_hash"].notna(),
            "pt:"
            + work["prompt_tokens"].astype(str)
            + ":ct:"
            + work["completion_tokens"].astype(str),
        )
        work["_hash_based"] = work["prefix_hash"].notna()

        # R-D6-AGG: one result per SESSION — waste summed over its storm clusters
        results: list[
            tuple[float, bool, int, list[pd.DataFrame], list[dict[str, object]], str]
        ] = []
        for tag, tag_group in work.groupby("tag", sort=True):
            for session in split_on_gap(tag_group, s.d6_session_gap_s):
                wasted = 0.0
                largest = 0
                all_hash_based = True
                session_clusters: list[pd.DataFrame] = []
                cluster_details: list[dict[str, object]] = []
                for (model, _identity), group in session.groupby(["model", "_identity"], sort=True):
                    if len(group) < s.d4_dup_min:
                        continue
                    for cluster in _clusters(group, s.d4_window_s):
                        if len(cluster) < s.d4_dup_min:
                            continue
                        costs = cluster["cost_usd"].dropna()
                        if len(costs) == 0:
                            continue  # unpriced model: waste unknowable for this cluster
                        # priced rows only, for BOTH count and mean: unpriced rows
                        # in a mixed cluster contribute no imputed waste
                        # (conservative; G3 cold-reviewer f.2). Cluster
                        # QUALIFICATION still uses all rows.
                        cluster_waste = (len(costs) - 1) * float(costs.mean())
                        if cluster_waste <= 0:
                            continue
                        wasted += cluster_waste
                        largest = max(largest, len(cluster))
                        all_hash_based &= bool(cluster["_hash_based"].iloc[0])
                        session_clusters.append(cluster.drop(columns=["_identity", "_hash_based"]))
                        cluster_details.append(
                            {
                                "model": str(model),
                                "start_ts": cluster["ts"].min().isoformat(),
                                "calls": len(cluster),
                                "observed_waste_usd": cluster_waste,
                            }
                        )
                if wasted <= 0:
                    continue
                results.append(
                    (wasted, all_hash_based, largest, session_clusters, cluster_details, str(tag))
                )

        results.sort(key=lambda r: -r[0])
        factor = monthly_factor(ctx.observed_days)
        findings: list[Finding] = []
        for i, (wasted, hash_based, largest, session_clusters, cluster_details, tag) in enumerate(
            results, start=1
        ):
            n_calls = sum(len(c) for c in session_clusters)
            models = sorted({str(d["model"]) for d in cluster_details})
            findings.append(
                Finding(
                    id=f"D4-{i:03d}",
                    detector=self.name,
                    severity=(Severity.HIGH if largest >= HIGH_SEVERITY_CLUSTER else Severity.MED),
                    monthly_cost_impact_usd=wasted * factor,
                    confidence=Confidence.CONSERVATIVE if hash_based else Confidence.ESTIMATED,
                    fix_text=(
                        f"Near-identical calls repeated in bursts on {', '.join(models)} "
                        f"(tag '{tag}': {len(session_clusters)} burst(s) in one session, "
                        f"{n_calls} calls, largest burst {largest}). Add retry backoff "
                        "with jitter, deduplicate in-flight requests, and cache the "
                        "first response for identical inputs within the burst window."
                    ),
                    evidence=sample_evidence_across(
                        session_clusters, note="near-identical call in burst"
                    ),
                    detail={"clusters": cluster_details},
                )
            )
        return findings
