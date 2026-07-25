"""Detector D10 — spend anomaly (founder 2026-07-25, "dynamic analysis based on logs").

Deterministic statistical anomaly detection: flags DAYS whose spend is a robust
statistical outlier versus the audit's OWN daily-spend baseline — the "dynamic
analysis" net that catches unusual cost events (runaway jobs, backfills, a job
sent to the wrong pricey model, a load test) the eight fixed-PATTERN detectors
cannot name. The comparison is TEMPORAL — each day against the account's own
typical day — so a legitimately heavier ROUTE or MODEL is never mistaken for a
spike (that is a cross-sectional distinction the pattern detectors own).
Enterprise FinOps-standard cost anomaly detection, done with explainable robust
statistics — no trained model, no LLM.

Robust by construction (median + MAD, not mean + std): the median and the median
absolute deviation are unmoved by the very spike we are hunting, so a spike can
never inflate the baseline and hide itself (which mean/std would let it do, and
which two mutually-masking spikes would exploit).

Two independent gates, each guarding a distinct false positive: a day flags only
when it is a strong robust outlier (>= D10_Z_THRESHOLD MADs above the median day,
or — on a perfectly flat baseline where the robust z is undefined — carried by the
materiality gate) AND materially above the typical day (>= D10_SPIKE_MULT x the
median). Both gates are scale-free (a z-score and a ratio), so they neither
over-fire on tiny accounts nor — the earlier excess-share-of-total design's flaw —
suppress a real spike on a long audit whose window dilutes its dollar share.

CAVEAT (honest limitation): the baseline is a single window-wide median, with no
day-of-week / seasonal model yet. A LEGITIMATELY recurring heavy day — a scheduled
weekly batch — will therefore re-flag each occurrence; that is exactly why the
finding asks the reader to VERIFY the event ("a launch, a backfill") rather than
asserting waste. Day-of-week / seasonal baselining is a planned refinement (BACKLOG).

Informational — carries $0 claimed saving, exactly like D8. An anomaly is a
POINTER to verify, not a promise: we do not know the fix for an unnamed spike, so
we never invent a saving number for it (the founder's precision bar). When the
spike WAS waste, the pattern detectors (D4 retry storm, D6 chatty loop, D1 wrong
model) price the recoverable part on the same day — D10 and they are complementary
lenses, temporal versus pattern, not duplicates.

Needs enough days to define "normal" (>= D10_MIN_DAYS) and per-request timestamps,
so it is honestly DORMANT on short or aggregate inputs: INACTIVE_ON_AGGREGATE, and
a sub-week window produces nothing rather than a fabricated outlier.

Not a new pricing estimator (it only sums cost_usd the coster already computed and
does statistics on the daily totals), so no rate golden is owed — but the anomaly
math is pinned by test_rules TestD10 against hand-derived values (CLAUDE.md rule 4
spirit). Engine-pure: no network/LLM (T-NFR-01).
"""

from __future__ import annotations

import pandas as pd

from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    Finding,
    Severity,
    make_evidence,
)

# MAD -> sigma for approximately-normal data (the standard robust-scale constant).
_MAD_TO_SIGMA = 1.4826
# Loudness by the deviation's OWN magnitude (how many x a typical day) — scale-free
# and anomaly-native, NOT the monthly-USD scale the savings detectors use (an
# anomaly makes no monthly claim to scale). A day 10x+ your normal is loud.
_SEVERITY_HIGH_MULT = 10.0
_SEVERITY_MED_MULT = 4.0


def _robust_z(value: float, median: float, mad: float) -> float | None:
    """Robust z-score: MADs above the median. None when the baseline has no
    spread (MAD == 0) — the materiality (multiple) gate carries it there."""
    sigma = _MAD_TO_SIGMA * mad
    return (value - median) / sigma if sigma > 0 else None


def _severity(multiple: float) -> Severity:
    if multiple >= _SEVERITY_HIGH_MULT:
        return Severity.HIGH
    if multiple >= _SEVERITY_MED_MULT:
        return Severity.MED
    return Severity.LOW


class D10SpendAnomaly:
    name = "d10_spend_anomaly"

    def run(self, frame: pd.DataFrame, ctx: DetectorContext) -> list[Finding]:
        s = ctx.settings
        if len(frame) == 0:
            return []
        # Unpriced rows carry NaN cost — drop them so the daily totals are honest.
        rows = frame.dropna(subset=["cost_usd"])
        if len(rows) == 0:
            return []
        by_day = rows.groupby(rows["ts"].dt.date)["cost_usd"].sum().sort_index()
        # A weekly baseline is the smallest window in which "normal" is meaningful;
        # below it we stay silent rather than call a spike on two or three days.
        if len(by_day) < s.d10_min_days:
            return []
        median = float(by_day.median())
        if median <= 0:
            return []  # more than half the days spent nothing: no baseline to deviate from
        mad = float((by_day - median).abs().median())

        findings: list[Finding] = []
        # Chronological order: numbering the ids by date reads as a timeline
        # (all D10 findings share $0 impact, so id is their stable sort key).
        for day, spend in by_day.items():
            spend = float(spend)
            if spend <= median:
                continue
            multiple = spend / median
            z = _robust_z(spend, median, mad)
            # Two independent gates: statistical (a strong robust outlier — or, on a
            # perfectly flat baseline where z is undefined, carried by materiality)
            # AND materiality (meaningfully above the typical day, not a hair over a
            # razor-tight baseline). Both scale-free, so window length never dilutes
            # a real spike out of range and a tiny account never over-fires.
            statistical = z is None or z >= s.d10_z_threshold
            material = multiple >= s.d10_spike_mult
            if not (statistical and material):
                continue

            excess = spend - median
            sub = rows[rows["ts"].dt.date == day].sort_values("cost_usd", ascending=False)
            top_model = str(sub.groupby("model")["cost_usd"].sum().idxmax())
            named = sub[sub["tag"].astype(str).str.strip() != ""]
            top_route = str(named.groupby("tag")["cost_usd"].sum().idxmax()) if len(named) else None
            route_phrase = f" on route '{top_route}'" if top_route else ""
            findings.append(
                Finding(
                    id=f"D10-{len(findings) + 1:03d}",
                    detector=self.name,
                    # loudness = the deviation's own magnitude (multiple), not a
                    # monthly-USD projection (an anomaly makes no monthly claim).
                    severity=_severity(multiple),
                    monthly_cost_impact_usd=0.0,  # a pointer, never a claimed saving
                    confidence=Confidence.ESTIMATED,
                    fix_text=(
                        f"On {day} your LLM spend was ${spend:,.2f} — {multiple:.1f}x your "
                        f"typical day (${median:,.2f}), about ${excess:,.2f} above normal in a "
                        f"single day, driven mainly by {top_model}{route_phrase}. This is an "
                        "unusual cost event the pattern detectors don't name: check it was "
                        "intended — a launch, a backfill, a load test. If it was a runaway job, "
                        "a retry storm, or a job sent to the wrong (pricier) model, that spend "
                        "is recoverable and likely to recur. No saving is claimed here; this "
                        "points you at where to look."
                    ),
                    evidence=make_evidence(sub, note="spend spike"),
                    detail={
                        "model": top_model,
                        "day": str(day),
                        "day_spend_usd": spend,
                        "median_day_spend_usd": median,
                        "multiple": multiple,
                        "excess_usd": excess,
                        "robust_z": z,
                        "top_route": top_route,
                    },
                )
            )
        return findings
