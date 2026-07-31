"""FR-36 behaviour lens v1 (docs/03-LLD.md §9.3) — deterministic per-route
workload-shape classification.

Pins the exact rationale strings `classify` emits (the /breakdown chip and the
tokenomics.json artifact must agree word-for-word with these templates), the
most-specific-first precedence order, config-injected thresholds, and the
honest STEADY/empty fallbacks. Frames are built by hand with fixed timestamps
so every threshold crossing is hand-derivable — no randomness anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.dashboard.shapes import ShapeClass, classify, compute_shapes

pytestmark = [pytest.mark.verifies_requirement("FR-36")]

BASE = datetime(2026, 7, 1, tzinfo=UTC)


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    defaults = {
        "model": "claude-sonnet-5",
        "tag": "chat",
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "prefix_hash": None,
    }
    frame = pd.DataFrame([{**defaults, **r} for r in rows])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="test", secret_key="t", database_url="sqlite://", _env_file=None)


# --------------------------------------------------------------------- goldens
# One frame per ShapeClass. Counts are hand-derived in the comments beside each
# frame so the expected rationale string can be checked verbatim, not just the
# class.


def _burst_golden() -> pd.DataFrame:
    # 5 rows, same (model, prefix_hash) identity, no cache activity.
    # Anchor clustering (window 120s) from t=0: rows at 0/30/60/90s are all
    # within 120s of the cluster start -> cluster size 4; the row at 600s
    # starts a fresh cluster of size 1 (600 - 0 = 600 > 120). best = 4 >= 3
    # (shape_burst_min) -> RETRY_BURST.
    offsets = [0, 30, 60, 90, 600]
    return _frame(
        [
            {
                "ts": BASE + timedelta(seconds=o),
                "prompt_tokens": 1000,
                "completion_tokens": 500,  # not "small" (>= 300) - keeps AGENT_LOOP silent
                "prefix_hash": "burstprefix",
            }
            for o in offsets
        ]
    )


def _loop_golden() -> pd.DataFrame:
    # 8 rows, distinct prompt_tokens each (so no two share a burst identity;
    # every per-identity cluster size is 1, well under shape_burst_min=3),
    # completion_tokens=100 < 300 (small), spaced 60s apart across 420s total
    # (<= run window 600s) -> one cluster of size 8 >= 8 (shape_loop_min).
    return _frame(
        [
            {
                "ts": BASE + timedelta(seconds=60 * i),
                "prompt_tokens": 1000 + i,
                "completion_tokens": 100,
            }
            for i in range(8)
        ]
    )


def _growth_golden() -> pd.DataFrame:
    # 8 rows, no prefix_hash, completion_tokens=500 (not small, silences
    # AGENT_LOOP). Rows spaced 200s apart so no two identical-identity rows
    # (same model:prompt:completion) ever land in the same 120s burst window
    # (200 > 120 every time) -> burst stays silent. First quarter (idx 0,1,
    # prompt=1000,1000) median = 1000; last quarter (idx 6,7, prompt=3000,3000)
    # median = 3000; 3000 >= 1000 * 2.0 -> CONTEXT_GROWTH.
    prompts = [1000, 1000, 1000, 1000, 1000, 1000, 3000, 3000]
    return _frame(
        [
            {"ts": BASE + timedelta(seconds=200 * i), "prompt_tokens": p, "completion_tokens": 500}
            for i, p in enumerate(prompts)
        ]
    )


def _cache_golden() -> pd.DataFrame:
    # 25 rows, same prefix_hash, prompt_tokens=2000 (median >= 1024), no
    # cache reads ever, spaced 150s apart so every burst cluster is size 1
    # (150 > 120 window) -> burst stays silent. completion_tokens=500 (not
    # small) silences AGENT_LOOP; constant prompt_tokens silences
    # CONTEXT_GROWTH (ratio 1.0x). n=25 >= 25 (shape_cache_min_repeats),
    # median 2000 >= 1024, sum(cached_tokens)=0 -> UNCLAIMED_CACHE.
    return _frame(
        [
            {
                "ts": BASE + timedelta(seconds=150 * i),
                "prompt_tokens": 2000,
                "completion_tokens": 500,
                "prefix_hash": "cacheprefix",
            }
            for i in range(25)
        ]
    )


def _steady_golden() -> pd.DataFrame:
    # 3 rows, distinct prompt_tokens (burst identities all size 1), no
    # prefix_hash (UNCLAIMED_CACHE structurally can't see them), n=3 < 8
    # (below shape_growth_min_calls), completion_tokens=500 (not small).
    # Nothing crosses -> STEADY, naming its own call count.
    return _frame(
        [
            {"ts": BASE + timedelta(seconds=60 * i), "prompt_tokens": 1000 + 500 * i}
            for i in range(3)
        ]
    )


class TestShapeGoldens:
    def test_retry_burst(self, settings: Settings) -> None:
        result = classify(_burst_golden(), settings)
        assert result.cls == ShapeClass.RETRY_BURST
        assert result.rationale == "4 near-identical calls within 120 s (threshold: 3)"

    def test_agent_loop(self, settings: Settings) -> None:
        result = classify(_loop_golden(), settings)
        assert result.cls == ShapeClass.AGENT_LOOP
        assert result.rationale == "8 calls under 300 output tokens within 600 s (threshold: 8)"

    def test_context_growth(self, settings: Settings) -> None:
        result = classify(_growth_golden(), settings)
        assert result.cls == ShapeClass.CONTEXT_GROWTH
        # "input" not "prompt" (FR-22 marker tripwire reword, T-F3 follow-up):
        # the shipped test_developer_platform.py::test_fr22_shape_counts_and_dollars_only
        # asserts the whole breakdown response text contains no "prompt" substring.
        assert result.rationale == (
            "median input grew 1,000 → 3,000 tokens (3.0x) from the first to "
            "the last quarter of the window (threshold: 2.0x)"
        )

    def test_unclaimed_cache(self, settings: Settings) -> None:
        result = classify(_cache_golden(), settings)
        assert result.cls == ShapeClass.UNCLAIMED_CACHE
        # "input tokens" not "prompt tokens" (same FR-22 tripwire reword).
        assert result.rationale == (
            "same prefix sent 25x at median 2,000 input tokens with 0 cached "
            "tokens read (threshold: 25 repeats at >= 1,024 tokens)"
        )

    def test_steady(self, settings: Settings) -> None:
        result = classify(_steady_golden(), settings)
        assert result.cls == ShapeClass.STEADY
        assert result.rationale == (
            "no loop, burst, growth or cache signal crossed its threshold across 3 calls"
        )


class TestShapeDeterminism:
    def test_same_frame_twice_is_identical(self, settings: Settings) -> None:
        frame = _growth_golden()
        first = classify(frame, settings)
        second = classify(frame, settings)
        assert first == second

    def test_row_order_shuffle_is_identical(self, settings: Settings) -> None:
        frame = _cache_golden()
        baseline = classify(frame, settings)
        shuffled = frame.sample(frac=1, random_state=7).reset_index(drop=True)
        assert classify(shuffled, settings) == baseline


class TestShapePrecedence:
    def test_burst_and_loop_both_cross_burst_wins(self, settings: Settings) -> None:
        # 8 identical small no-cache calls, 15s apart, same prefix_hash:
        # - burst: one identity group, all 8 within 120s of the cluster start
        #   (7 * 15s = 105s <= 120s) -> best = 8 >= 3 (shape_burst_min).
        # - loop: completion_tokens=100 < 300, same 8 rows within the 600s run
        #   window -> best = 8 >= 8 (shape_loop_min) - would ALSO cross.
        # classify() tries _burst before _loop, so RETRY_BURST must win.
        frame = _frame(
            [
                {
                    "ts": BASE + timedelta(seconds=15 * i),
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "prefix_hash": "precprefix",
                }
                for i in range(8)
            ]
        )
        result = classify(frame, settings)
        assert result.cls == ShapeClass.RETRY_BURST
        assert result.rationale == "8 near-identical calls within 120 s (threshold: 3)"


class TestShapeConfigInjection:
    def test_loop_min_raised_above_run_size_reclassifies_steady(self, settings: Settings) -> None:
        raised = settings.model_copy(update={"shape_loop_min": 9})
        result = classify(_loop_golden(), raised)
        assert result.cls == ShapeClass.STEADY
        assert result.rationale == (
            "no loop, burst, growth or cache signal crossed its threshold across 8 calls"
        )


class TestShapeCacheExclusion:
    def test_cache_active_rows_excluded_from_burst(self, settings: Settings) -> None:
        # Same shape as the RETRY_BURST golden, but every row now has a
        # nonzero cached_tokens - the burst signal's no-cache filter drops
        # all 5 rows, so _burst returns None outright (never even reaches
        # clustering). Nothing else crosses (n=5 < 8 growth min, prefix
        # group n=5 < 25 cache min) -> STEADY, naming the 5 calls.
        frame = _burst_golden()
        frame["cached_tokens"] = 50
        result = classify(frame, settings)
        assert result.cls != ShapeClass.RETRY_BURST
        assert result.cls == ShapeClass.STEADY
        assert result.rationale == (
            "no loop, burst, growth or cache signal crossed its threshold across 5 calls"
        )


class TestShapeEmpty:
    def test_empty_frame_is_steady_no_calls_observed(self, settings: Settings) -> None:
        result = classify(pd.DataFrame(), settings)
        assert result.cls == ShapeClass.STEADY
        assert result.rationale == "no calls observed"

    def test_compute_shapes_of_empty_frame(self, settings: Settings) -> None:
        assert compute_shapes(pd.DataFrame(), settings) == {"schema": 1, "by_route": []}


class TestComputeShapes:
    def test_multi_route_sorted_untagged_and_nan_cost_still_classified(
        self, settings: Settings
    ) -> None:
        # Three routes, each STEADY (too few rows / too uniform to cross any
        # threshold): "zeta" (3 rows), "" (1 row, maps to "(untagged)"), and
        # "alpha" (2 rows, BOTH with cost_usd=NaN - unpriced but still counted).
        rows = [
            {"ts": BASE, "tag": "zeta", "prompt_tokens": 1000, "cost_usd": 1.0},
            {
                "ts": BASE + timedelta(seconds=60),
                "tag": "zeta",
                "prompt_tokens": 1500,
                "cost_usd": 2.0,
            },
            {
                "ts": BASE + timedelta(seconds=120),
                "tag": "zeta",
                "prompt_tokens": 2000,
                "cost_usd": float("nan"),
            },
            {
                "ts": BASE,
                "tag": "",
                "prompt_tokens": 800,
                "completion_tokens": 400,
                "cost_usd": 3.0,
            },
            {"ts": BASE, "tag": "alpha", "prompt_tokens": 1000, "cost_usd": float("nan")},
            {
                "ts": BASE + timedelta(seconds=60),
                "tag": "alpha",
                "prompt_tokens": 1005,
                "cost_usd": float("nan"),
            },
        ]
        result = compute_shapes(_frame(rows), settings)
        assert result == {
            "schema": 1,
            "by_route": [
                {
                    "route": "(untagged)",
                    "shape": "STEADY",
                    "rationale": (
                        "no loop, burst, growth or cache signal crossed its threshold "
                        "across 1 calls"
                    ),
                },
                {
                    "route": "alpha",
                    "shape": "STEADY",
                    "rationale": (
                        "no loop, burst, growth or cache signal crossed its threshold "
                        "across 2 calls"
                    ),
                },
                {
                    "route": "zeta",
                    "shape": "STEADY",
                    "rationale": (
                        "no loop, burst, growth or cache signal crossed its threshold "
                        "across 3 calls"
                    ),
                },
            ],
        }
        # NaN cost_usd rows were not dropped: "alpha" (fully unpriced) still appears.
        routes = {r["route"] for r in result["by_route"]}
        assert {"(untagged)", "alpha", "zeta"} == routes
