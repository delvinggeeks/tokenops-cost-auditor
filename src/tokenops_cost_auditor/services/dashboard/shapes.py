"""FR-36 behaviour lens — deterministic per-route workload-shape classification
(docs/03-LLD.md §9.3; docs/12 INTENT LAW, BEHAVIORAL level).

`classify` reads ONLY counts, timing, model and cache columns of the audited
frame — never content (FR-22 by construction: no text exists here to consume).
No probabilities, no inference: every class is a threshold crossing, and the
rationale is a fixed template naming the exact counts that fired it. Thresholds
live in Settings (the detector-thresholds idiom, LLD §3) and are injected by
the caller — this module reads no environment and does no I/O.

Each signal mirrors the shipped detector it shadows, so the chip on /breakdown
agrees with the findings list: RETRY_BURST ~ D4 (near-identical identity key,
cache-active rows excluded), AGENT_LOOP ~ D6 (runs of small completions),
CONTEXT_GROWTH ~ D3's bloat family (prompt growth over the window),
UNCLAIMED_CACHE ~ D2 (repeated prefix, zero cache reads). Precedence is
most-specific-first — BURST before LOOP before GROWTH before CACHE — first
crossing wins; STEADY is the honest fallback, stated with its call count.

Engine-pure: no network/LLM imports (T-NFR-01 discipline; import-guard
covers this module explicitly).

Rationale vocabulary: "input tokens", never "prompt"/"completion" — these
strings ride the read API verbatim, and the FR-22 marker tripwire
(test_developer_platform fr22 shape tests) treats those words anywhere in a
response body as a text-leak signal. Counts-speak here matches the API's own
field vocabulary (input_tokens / output_tokens).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from tokenops_cost_auditor.config import Settings

UNTAGGED = "(untagged)"

SHAPES_SCHEMA = 1


class ShapeClass(Enum):
    AGENT_LOOP = "AGENT_LOOP"
    RETRY_BURST = "RETRY_BURST"
    CONTEXT_GROWTH = "CONTEXT_GROWTH"
    UNCLAIMED_CACHE = "UNCLAIMED_CACHE"
    STEADY = "STEADY"


@dataclass(frozen=True)
class ShapeResult:
    cls: ShapeClass
    rationale: str


# Presentation copy (docs/12 COPY LAW, dev depth): fix-first — name the fix,
# never the blame. Static text at the services layer so the page and any future
# surface render the SAME words (the detector_copy.py idiom). The API carries
# only class + rationale; this copy is the HTML surface's voice.
SHAPE_COPY: dict[str, dict[str, str]] = {
    "AGENT_LOOP": {
        "label": "Agent loop",
        "fix": "Batch the small steps or cache the shared context — same output, "
        "fewer round-trips.",
        "tone": "estimate",
    },
    "RETRY_BURST": {
        "label": "Retry burst",
        "fix": "Add backoff or dedupe the trigger — you're paying for the same answer "
        "more than once.",
        "tone": "waste",
    },
    "CONTEXT_GROWTH": {
        "label": "Context growth",
        "fix": "Trim or summarize history as it accumulates — same answers, smaller prompts.",
        "tone": "estimate",
    },
    "UNCLAIMED_CACHE": {
        "label": "Unclaimed cache",
        "fix": "Mark the stable prefix for provider caching — repeat calls read it at "
        "a fraction of the price.",
        "tone": "estimate",
    },
    # Steady is a classification, not a money claim — neutral tone, no fix line
    # (green stays reserved for verified dollars).
    "STEADY": {"label": "Steady", "fix": "", "tone": "neutral"},
}


def _anchor_clusters(times: list[pd.Timestamp], window_s: int) -> list[int]:
    """Cluster sizes under the anchor rule (D4/D6 idiom): a cluster collects
    consecutive time-sorted rows within `window_s` of the CLUSTER START —
    deterministic, no sliding ambiguity."""
    sizes: list[int] = []
    start = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or (times[i] - times[start]).total_seconds() > window_s:
            sizes.append(i - start)
            start = i
    return sizes


def _burst(rows: pd.DataFrame, s: Settings) -> ShapeResult | None:
    """RETRY_BURST ~ D4: near-identical calls clustered in a short window.
    Cache-active rows are session continuations, not blind duplicates (UAT-1
    dogfood law) — excluded before identity grouping. Identity = prefix_hash
    when present (conservative), else the exact token shape."""
    no_cache = (rows["cached_tokens"].fillna(0) == 0) & (rows["cache_write_tokens"].fillna(0) == 0)
    eligible = rows[no_cache]
    if eligible.empty:
        return None
    work = eligible.copy()
    work["_identity"] = work["prefix_hash"].where(
        work["prefix_hash"].notna(),
        work["model"].astype(str)
        + ":"
        + work["prompt_tokens"].astype(str)
        + ":"
        + work["completion_tokens"].astype(str),
    )
    best = 0
    for _, group in work.groupby(["model", "_identity"], sort=True):
        sizes = _anchor_clusters(group.sort_values("ts")["ts"].tolist(), s.shape_burst_window_s)
        best = max(best, max(sizes))
    if best >= s.shape_burst_min:
        return ShapeResult(
            ShapeClass.RETRY_BURST,
            f"{best} near-identical calls within {s.shape_burst_window_s} s "
            f"(threshold: {s.shape_burst_min})",
        )
    return None


def _loop(rows: pd.DataFrame, s: Settings) -> ShapeResult | None:
    """AGENT_LOOP ~ D6: a run of small completions inside the run window."""
    small = rows[rows["completion_tokens"] < s.shape_small_completion_t]
    if small.empty:
        return None
    sizes = _anchor_clusters(small.sort_values("ts")["ts"].tolist(), s.shape_run_window_s)
    best = max(sizes)
    if best >= s.shape_loop_min:
        return ShapeResult(
            ShapeClass.AGENT_LOOP,
            f"{best} calls under {s.shape_small_completion_t} output tokens within "
            f"{s.shape_run_window_s} s (threshold: {s.shape_loop_min})",
        )
    return None


def _growth(rows: pd.DataFrame, s: Settings) -> ShapeResult | None:
    """CONTEXT_GROWTH: median prompt size of the last quarter of the window vs
    the first — monotonic-growth signal without curve fitting (docs/12:
    "monotonic prompt growth = context bloat")."""
    n = len(rows)
    if n < s.shape_growth_min_calls:
        return None
    ordered = rows.sort_values("ts")["prompt_tokens"]
    # max(1, ...): at a user-lowered min_calls, q=0 would make iloc[-q:] the
    # WHOLE series (-0 == 0), not an empty slice (G-T-F3 cold-reviewer f.2).
    q = max(1, n // 4)
    first = float(ordered.iloc[:q].median())
    last = float(ordered.iloc[-q:].median())
    if first > 0 and last >= first * s.shape_growth_mult:
        return ShapeResult(
            ShapeClass.CONTEXT_GROWTH,
            f"median input grew {int(first):,} → {int(last):,} tokens "
            f"({last / first:.1f}x) from the first to the last quarter of the window "
            f"(threshold: {s.shape_growth_mult:.1f}x)",
        )
    return None


def _unclaimed_cache(rows: pd.DataFrame, s: Settings) -> ShapeResult | None:
    """UNCLAIMED_CACHE ~ D2: one prefix repeats at cacheable size and none of
    those calls ever reads cache."""
    hashed = rows[rows["prefix_hash"].notna()]
    if hashed.empty:
        return None
    for _, bucket in hashed.groupby("prefix_hash", sort=True):
        n = len(bucket)
        med = float(bucket["prompt_tokens"].median())
        reads = float(bucket["cached_tokens"].fillna(0).sum())
        if n >= s.shape_cache_min_repeats and med >= s.shape_cache_min_prompt_tokens and reads == 0:
            return ShapeResult(
                ShapeClass.UNCLAIMED_CACHE,
                f"same prefix sent {n:,}x at median {int(med):,} input tokens with "
                f"0 cached tokens read (threshold: {s.shape_cache_min_repeats} repeats "
                f"at >= {s.shape_cache_min_prompt_tokens:,} tokens)",
            )
    return None


def classify(route_rows: pd.DataFrame, settings: Settings) -> ShapeResult:
    """One route's workload shape (LLD §9.3). First threshold crossing wins,
    most-specific-first; STEADY is the fallback and names the call count it
    stands on — never a default silently applied to unclassifiable data."""
    n = len(route_rows)
    if n == 0:
        return ShapeResult(ShapeClass.STEADY, "no calls observed")
    for signal in (_burst, _loop, _growth, _unclaimed_cache):
        result = signal(route_rows, settings)
        if result is not None:
            return result
    return ShapeResult(
        ShapeClass.STEADY,
        f"no loop, burst, growth or cache signal crossed its threshold across {n:,} calls",
    )


def _route_name(tag: object) -> str:
    return str(tag) if str(tag).strip() else UNTAGGED


def compute_shapes(frame: pd.DataFrame, settings: Settings) -> dict[str, object]:
    """The artifact's `shapes` block: every observed route classified, keyed by
    the same route naming as tokenomics.by_route so the page joins 1:1.
    Classification runs on ALL observed rows (priced or not) — behaviour needs
    counts and timing, not a rate card. Schema-versioned and additive: an
    artifact without this block is a pre-feature audit and renders as an honest
    null downstream, never a fabricated STEADY."""
    by_route: list[dict[str, str]] = []
    if len(frame):
        for tag, group in frame.groupby("tag", sort=True):
            result = classify(group, settings)
            by_route.append(
                {
                    "route": _route_name(tag),
                    "shape": result.cls.value,
                    "rationale": result.rationale,
                }
            )
    by_route.sort(key=lambda r: str(r["route"]))
    return {"schema": SHAPES_SCHEMA, "by_route": by_route}
