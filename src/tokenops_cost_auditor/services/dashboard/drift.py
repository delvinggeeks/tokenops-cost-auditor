"""Cross-audit efficiency drift (founder 2026-07-25, depth engine — the "drift"
half of "anomaly & drift detection").

Pure, deterministic comparison of one audit's tokenomics vitals against the
PRIOR audit's — like-to-like over time, so a change IS a real trend, not the
cross-sectional "this route is heavier" confound. Reads two tokenomics.json
artifacts (the exact figures the runner already computed); every number here is
a subtraction or a ratio of them — no model, no estimate. It answers the
enterprise FinOps question the single-audit breakdown cannot: "is our AI spend
getting more or less efficient over time?"

Direction is judged ONLY where "good" is unambiguous: cost-per-request and
cost-per-1k-output rising is worse; cache-hit-rate falling is worse. Monthly
spend is shown as CONTEXT with no better/worse verdict — more spend can simply
mean more usage, and calling that a regression would be dishonest. A change
smaller than the material threshold is "flat" (noise, not a trend).

Not a new estimator (it only diffs already-priced tokenomics figures), so no
rate golden is owed — pinned by tests/test_drift.py hand-derived deltas and
directions. Engine-adjacent but presentation-layer: no network/LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

# A relative change below this is treated as flat — noise, not a real trend.
_MATERIAL_PCT = 0.05


@dataclass(frozen=True)
class DriftMetric:
    label: str
    current: float
    prior: float
    delta: float  # current - prior
    pct_change: float  # delta / prior (0.0 when prior == 0)
    # "better" | "worse" | "flat" (judged) · "up" | "down" (context) · "new" (no baseline)
    direction: str
    kind: str  # "money" | "rate" — a formatting hint for the template


@dataclass(frozen=True)
class Drift:
    prior_audit_id: str
    metrics: tuple[DriftMetric, ...]
    # labels of the efficiency metrics that got MATERIALLY worse — drives the
    # "your unit economics are slipping" callout. Empty when nothing regressed.
    regressions: tuple[str, ...]


def _pct(delta: float, prior: float) -> float:
    return delta / prior if prior else 0.0


def _metric(label: str, cur: float, prior: float, good: bool | None, kind: str) -> DriftMetric:
    """One compared vital. `good`: True = higher is better, False = lower is
    better, None = context only (no better/worse verdict — e.g. total spend).

    A ZERO prior has no percentage baseline to compare against — a prior audit with
    $0 priced spend makes a cost ratio undefined — so it is reported as a NEW
    measurement, NEVER a dishonest better/worse verdict (cold gate). "flat" when both
    are zero."""
    cur, prior = float(cur), float(prior)
    delta = cur - prior
    pct = _pct(delta, prior)
    if prior == 0:
        direction = "flat" if cur == 0 else "new"
    elif abs(pct) < _MATERIAL_PCT:
        direction = "flat"  # a sub-material change is noise, not a trend
    elif good is None:
        direction = "up" if delta > 0 else "down"
    else:
        direction = "better" if (delta > 0) == good else "worse"
    return DriftMetric(label, cur, prior, delta, pct, direction, kind)


def compute(current: dict[str, object], prior: dict[str, object], prior_audit_id: str) -> Drift:
    """Drift of `current` tokenomics vs `prior` (both are tokenomics.json dicts —
    dataclasses.asdict(Tokenomics))."""

    def cur(key: str) -> float:
        return float(current[key])  # type: ignore[arg-type]

    def pri(key: str) -> float:
        return float(prior[key])  # type: ignore[arg-type]

    metrics = (
        # context: more spend can just mean more usage — never judged a regression
        _metric("Monthly spend", cur("monthly_spend_usd"), pri("monthly_spend_usd"), None, "money"),
        _metric(
            "Cost per request", cur("cost_per_request"), pri("cost_per_request"), False, "money"
        ),
        _metric(
            "Cost per 1K output tokens",
            cur("cost_per_1k_out"),
            pri("cost_per_1k_out"),
            False,
            "money",
        ),
        _metric("Cache hit rate", cur("cache_hit_rate"), pri("cache_hit_rate"), True, "rate"),
    )
    regressions = tuple(m.label for m in metrics if m.direction == "worse")
    return Drift(prior_audit_id=prior_audit_id, metrics=metrics, regressions=regressions)
