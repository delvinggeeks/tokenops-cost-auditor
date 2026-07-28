"""Behaviour lens classifier — golden fixture per shape (FR-36; docs/03-LLD.md
§9.3). `classify()` is pure: given the counts/timing/model/cache columns of a
route's calls, it returns the exact class AND the exact rationale string —
pinned here the same way money math is pinned by a golden.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.dashboard.shapes import ShapeClass, classify

T0 = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


COLUMNS = ("ts", "model", "prompt_tokens", "completion_tokens", "cached_tokens", "prefix_hash")


def _rows(records: list[dict[str, object]]) -> pd.DataFrame:
    defaults = {
        "model": "claude-opus-4-8",
        "prompt_tokens": 500,
        "completion_tokens": 200,
        "cached_tokens": 0,
        "prefix_hash": "",
    }
    frame = pd.DataFrame([{**defaults, **r} for r in records], columns=COLUMNS)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


class TestShapeGoldens:
    def test_retry_burst(self) -> None:
        settings = make_settings()
        rows = _rows(
            [{"ts": T0 + timedelta(seconds=10 * i), "prefix_hash": "h-retry"} for i in range(5)]
        )
        result = classify(rows, settings)
        assert result.cls == ShapeClass.RETRY_BURST
        assert result.rationale == "5 near-identical calls repeated within 120s of each other"

    def test_agent_loop(self) -> None:
        settings = make_settings()
        rows = _rows(
            [
                {
                    "ts": T0 + timedelta(seconds=300 * i),
                    "prefix_hash": "h-loop",
                    "completion_tokens": 50,
                }
                for i in range(8)
            ]
        )
        result = classify(rows, settings)
        assert result.cls == ShapeClass.AGENT_LOOP
        assert result.rationale == (
            "8 small calls (<300 output tokens) with one repeated input signature seen 8 times"
        )

    def test_context_growth(self) -> None:
        settings = make_settings()
        rows = _rows(
            [
                {
                    "ts": T0 + timedelta(seconds=600 * i),
                    "prompt_tokens": 500 if i < 3 else 2000,
                    "completion_tokens": 400,
                    "prefix_hash": f"h-{i}",
                }
                for i in range(6)
            ]
        )
        result = classify(rows, settings)
        assert result.cls == ShapeClass.CONTEXT_GROWTH
        assert result.rationale == (
            "average input size grew from 500 to 2000 tokens across 6 calls "
            "(first half vs second half)"
        )

    def test_unclaimed_cache(self) -> None:
        settings = make_settings()
        rows = _rows(
            [
                {
                    "ts": T0 + timedelta(seconds=600 * i),
                    "prompt_tokens": 2000,
                    "completion_tokens": 400,
                    "cached_tokens": 0,
                    "prefix_hash": "h-cache",
                }
                for i in range(6)
            ]
        )
        result = classify(rows, settings)
        assert result.cls == ShapeClass.UNCLAIMED_CACHE
        assert result.rationale == (
            "one repeated input signature seen 6 times averaging 2000 tokens with only "
            "0% served from cache"
        )

    def test_steady(self) -> None:
        settings = make_settings()
        rows = _rows(
            [
                {
                    "ts": T0 + timedelta(seconds=900 * i),
                    "prompt_tokens": 800,
                    "completion_tokens": 400,
                    "prefix_hash": f"h-{i}",
                }
                for i in range(5)
            ]
        )
        result = classify(rows, settings)
        assert result.cls == ShapeClass.STEADY
        assert result.rationale == (
            "5 calls, no loop/retry/growth/cache-miss pattern crossed threshold"
        )

    def test_too_few_calls_is_steady_by_floor(self) -> None:
        settings = make_settings()
        rows = _rows([{"ts": T0 + timedelta(seconds=i)} for i in range(3)])
        result = classify(rows, settings)
        assert result.cls == ShapeClass.STEADY
        assert result.rationale == (
            "only 3 call(s) observed — below the 5-call floor to classify a shape"
        )

    def test_no_calls_is_steady(self) -> None:
        settings = make_settings()
        result = classify(_rows([]), settings)
        assert result.cls == ShapeClass.STEADY
        assert result.rationale == "no calls observed"
