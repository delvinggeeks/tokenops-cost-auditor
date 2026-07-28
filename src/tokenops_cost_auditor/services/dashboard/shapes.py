"""Behaviour lens — deterministic per-route workload-shape classifier
(FR-36; docs/01-REQUIREMENTS.md §H; docs/03-LLD.md §9.3).

Classifies a route's calls into ONE of five workload shapes from counts,
timing, model and cache fields ONLY — never prompt/completion content, so
there is nothing here for FR-22 to violate (no text column is ever read).
Ships beside tokenomics.py: pure pandas, no network, no LLM (the same
purity spirit as T-NFR-01, extended to this module by the import guard even
though services/dashboard sits outside that rule's literal scope).

Thresholds live in config.py (the detector-thresholds idiom already used by
D1-D10) — no magic numbers below. Several checks intentionally echo an
existing $-impact detector because a workload "shape" and a dollar finding
are two views of the same underlying pattern: RETRY_BURST echoes D4 (near-
identical calls clustered in time), AGENT_LOOP echoes D6 (small calls run
with a re-read prompt prefix), UNCLAIMED_CACHE echoes D2 (a repeated prefix
never hitting cache). CONTEXT_GROWTH has no detector analogue yet — it is a
purely behavioural signal (prompt size climbing turn over turn).

Priority order when more than one signal fires (first match wins — a route
matching several patterns is reported by its most actionable one):
RETRY_BURST > AGENT_LOOP > CONTEXT_GROWTH > UNCLAIMED_CACHE > STEADY.

`rationale` is always a fixed template naming the actual counts that fired
it — no probabilities, no inference, no free text.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import pandas as pd

from tokenops_cost_auditor.config import Settings


class ShapeClass(enum.StrEnum):
    AGENT_LOOP = "agent_loop"
    RETRY_BURST = "retry_burst"
    CONTEXT_GROWTH = "context_growth"
    UNCLAIMED_CACHE = "unclaimed_cache"
    STEADY = "steady"


# Chip copy for the /breakdown page (docs/12 COPY LAW, dev depth: fix-first —
# name the fix, not the blame). Fixed strings, keyed by class, never generated;
# `rationale` (above) is the evidence, this is the one-line "so what". Exposed
# as a Jinja global (`shape_copy`, main.py) so the template never invents copy.
SHAPE_COPY: dict[str, dict[str, str]] = {
    ShapeClass.AGENT_LOOP: {
        "label": "Agent loop",
        "fix": "Batch these calls — same output, fewer round-trips.",
    },
    ShapeClass.RETRY_BURST: {
        "label": "Retry burst",
        "fix": "Dedupe these calls — same output, fewer requests.",
    },
    ShapeClass.CONTEXT_GROWTH: {
        "label": "Context growth",
        "fix": "Trim or summarize context each turn — same output, smaller input.",
    },
    ShapeClass.UNCLAIMED_CACHE: {
        "label": "Unclaimed cache",
        "fix": "Make the repeated input cache-stable — same output, lower bill.",
    },
    ShapeClass.STEADY: {
        "label": "Steady",
        "fix": "No pattern to fix here — this route is behaving as expected.",
    },
}


@dataclass(frozen=True)
class ShapeResult:
    cls: ShapeClass
    rationale: str


def _max_burst(rows: pd.DataFrame, window_s: int) -> int:
    """Largest cluster of near-identical calls anchored to its start time
    (same anchor rule as D4's `_clusters`): identity is (model, prefix_hash)
    when a hash exists, else (model, prompt_tokens, completion_tokens)."""
    has_hash = rows["prefix_hash"].fillna("").astype(str) != ""
    key = pd.Series(index=rows.index, dtype=object)
    if has_hash.any():
        key.loc[has_hash] = list(
            zip(rows.loc[has_hash, "model"], rows.loc[has_hash, "prefix_hash"], strict=True)
        )
    if (~has_hash).any():
        key.loc[~has_hash] = list(
            zip(
                rows.loc[~has_hash, "model"],
                rows.loc[~has_hash, "prompt_tokens"],
                rows.loc[~has_hash, "completion_tokens"],
                strict=True,
            )
        )
    best = 0
    for _, group in rows.groupby(key, sort=False):
        times = group.sort_values("ts")["ts"].tolist()
        start = 0
        for i in range(1, len(times) + 1):
            if i == len(times) or (times[i] - times[start]).total_seconds() > window_s:
                best = max(best, i - start)
                start = i
    return best


def classify(route_rows: pd.DataFrame, settings: Settings) -> ShapeResult:
    """One route's calls -> its workload shape. Pure function: counts, `ts`,
    `model`, `prompt_tokens`, `completion_tokens`, `cached_tokens` and
    `prefix_hash` columns only."""
    n = len(route_rows)
    if n == 0:
        return ShapeResult(ShapeClass.STEADY, "no calls observed")
    if n < settings.shape_min_calls:
        return ShapeResult(
            ShapeClass.STEADY,
            f"only {n} call(s) observed — below the {settings.shape_min_calls}-call "
            "floor to classify a shape",
        )
    rows = route_rows.sort_values("ts")

    burst = _max_burst(rows, settings.shape_retry_window_s)
    if burst >= settings.shape_retry_dup_min:
        return ShapeResult(
            ShapeClass.RETRY_BURST,
            f"{burst} near-identical calls repeated within {settings.shape_retry_window_s}s "
            "of each other",
        )

    hashes = rows["prefix_hash"].fillna("").astype(str)
    hashes = hashes[hashes != ""]
    reread_counts = hashes.value_counts()
    max_reread = int(reread_counts.iloc[0]) if len(reread_counts) else 0
    small_t = settings.shape_agent_loop_small_completion_t
    small_calls = int((rows["completion_tokens"] < small_t).sum())
    loop_min = settings.shape_agent_loop_min_calls
    reread_min = settings.shape_agent_loop_reread_min
    if small_calls >= loop_min and max_reread >= reread_min:
        return ShapeResult(
            ShapeClass.AGENT_LOOP,
            f"{small_calls} small calls (<{small_t} output tokens) with one repeated input "
            f"signature seen {max_reread} times",
        )

    half = n // 2
    input_tokens = rows["prompt_tokens"]
    first_avg = float(input_tokens.iloc[:half].mean()) if half else float(input_tokens.iloc[0])
    second_avg = float(input_tokens.iloc[half:].mean())
    if first_avg > 0 and second_avg >= settings.shape_context_growth_mult * first_avg:
        return ShapeResult(
            ShapeClass.CONTEXT_GROWTH,
            f"average input size grew from {first_avg:.0f} to {second_avg:.0f} tokens across "
            f"{n} calls (first half vs second half)",
        )

    if max_reread >= settings.shape_unclaimed_cache_min_repeats:
        top_hash = reread_counts.index[0]
        top_rows = rows[rows["prefix_hash"] == top_hash]
        avg_input = float(top_rows["prompt_tokens"].mean())
        input_sum = float(top_rows["prompt_tokens"].sum())
        hit_rate = float(top_rows["cached_tokens"].sum()) / input_sum if input_sum > 0 else 0.0
        if (
            avg_input >= settings.shape_unclaimed_cache_min_prompt_tokens
            and hit_rate <= settings.shape_unclaimed_cache_max_hit_rate
        ):
            return ShapeResult(
                ShapeClass.UNCLAIMED_CACHE,
                f"one repeated input signature seen {max_reread} times averaging "
                f"{avg_input:.0f} tokens with only {hit_rate:.0%} served from cache",
            )

    return ShapeResult(
        ShapeClass.STEADY,
        f"{n} calls, no loop/retry/growth/cache-miss pattern crossed threshold",
    )
