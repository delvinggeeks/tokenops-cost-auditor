"""Cost computation over CallRecordFrames (FR-06) + reconciliation check (NFR-07).

Money math — 100% test coverage required; changes require a golden-file update
and spreadsheet diff in the commit message (CLAUDE.md rule 4).

Per-call formula (token semantics per R-Q4; prompt_tokens = TOTAL input):
    uncached  = max(prompt_tokens - cached_tokens - cache_write_tokens, 0)
    cost_usd  = (uncached * input
                 + cached_tokens * cache_read
                 + cache_write_tokens * cache_write
                 + completion_tokens * output) / 1e6
Rows whose model has no rate get cost_usd = NaN and the model is reported in
the unpriced list — the audit continues (PricingGapError path, docs/03 §8).
"""

from __future__ import annotations

import math

import pandas as pd

from tokenops_cost_auditor.services.pricing.table import PricingGapError, PricingTable

RECONCILE_TOLERANCE_PCT = 0.5  # NFR-07


def apply(table: PricingTable, frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return (frame with cost_usd column, sorted list of unpriced 'provider/model')."""
    frame = frame.copy()
    if len(frame) == 0:
        frame["cost_usd"] = pd.Series(dtype="float64")
        return frame, []

    days = frame["ts"].dt.date
    unpriced: set[str] = set()
    rate_cols: dict[str, list[float]] = {
        "input": [],
        "output": [],
        "cache_read": [],
        "cache_write": [],
    }

    cache: dict[tuple[str, str, object], tuple[float, float, float, float] | None] = {}
    for provider, model, day in zip(frame["provider"], frame["model"], days, strict=True):
        key = (provider, model, day)
        if key not in cache:
            try:
                rate = table.rate(provider, model, day)
                cache[key] = (rate.input, rate.output, rate.cache_read, rate.cache_write)
            except PricingGapError:
                cache[key] = None
                unpriced.add(f"{provider}/{model}")
        rates = cache[key]
        if rates is None:
            rates = (math.nan, math.nan, math.nan, math.nan)
        rate_cols["input"].append(rates[0])
        rate_cols["output"].append(rates[1])
        rate_cols["cache_read"].append(rates[2])
        rate_cols["cache_write"].append(rates[3])

    input_rate = pd.Series(rate_cols["input"], index=frame.index)
    output_rate = pd.Series(rate_cols["output"], index=frame.index)
    read_rate = pd.Series(rate_cols["cache_read"], index=frame.index)
    write_rate = pd.Series(rate_cols["cache_write"], index=frame.index)

    uncached = (frame["prompt_tokens"] - frame["cached_tokens"] - frame["cache_write_tokens"]).clip(
        lower=0
    )
    frame["cost_usd"] = (
        uncached * input_rate
        + frame["cached_tokens"] * read_rate
        + frame["cache_write_tokens"] * write_rate
        + frame["completion_tokens"] * output_rate
    ) / 1e6
    return frame, sorted(unpriced)


def total_spend(frame: pd.DataFrame) -> float:
    """The audit's headline total: sum of priced per-call costs (NaN rows excluded)."""
    return float(frame["cost_usd"].dropna().sum())


def reconcile(frame: pd.DataFrame, total: float | None = None) -> None:
    """NFR-07: an EXTERNALLY-TRACKED total reconciles with this frame within ±0.5%.

    `total` is the figure persisted/reported elsewhere (audits.total_spend_usd,
    report exec-summary); this check catches drift between that figure and the
    frame's recomputed aggregates. It does NOT independently validate the
    cost_usd column itself — by-model/by-day sums over the same column are
    algebraically its sum (modulo float ordering, which the tolerance absorbs);
    correctness of cost_usd is owned by the golden-file and property tests.
    With total=None it only asserts internal float-summation stability.
    NaN-cost rows (unpriced models) are excluded from every aggregate
    identically. Raises ValueError on violation.
    """
    if total is None:
        total = total_spend(frame)
    priced = frame.dropna(subset=["cost_usd"])
    if total == 0.0:
        if float(priced["cost_usd"].sum()) != 0.0:
            raise ValueError("cost reconciliation failed: parts nonzero but total is 0")
        return
    by_model = float(priced.groupby("model")["cost_usd"].sum().sum())
    by_day = float(priced.groupby(priced["ts"].dt.date)["cost_usd"].sum().sum())
    for name, part in (("by-model", by_model), ("by-day", by_day)):
        deviation_pct = abs(part - total) / abs(total) * 100.0
        if deviation_pct > RECONCILE_TOLERANCE_PCT:
            raise ValueError(
                f"cost reconciliation failed ({name}): parts {part!r} vs total {total!r} "
                f"deviates {deviation_pct:.4f}% > {RECONCILE_TOLERANCE_PCT}%"
            )
