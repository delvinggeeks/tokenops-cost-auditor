"""D3 pricing tests — T-PRC-01..05 (docs/05-TEST-PLAN.md §3)."""

import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tokenops_cost_auditor.services.pricing.coster import apply, reconcile, total_spend
from tokenops_cost_auditor.services.pricing.table import PricingGapError, PricingTable

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = PricingTable.load()


def make_frame(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "provider": "anthropic",
        "model": "claude-opus-4-8",
        "ts": datetime(2026, 6, 15, tzinfo=UTC),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
    }
    frame = pd.DataFrame([{**defaults, **row} for row in rows])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


class TestTPRC01RateLookup:
    def test_exact_lookup(self) -> None:
        rate = TABLE.rate("anthropic", "claude-opus-4-8", date(2026, 6, 15))
        assert (rate.input, rate.output) == (5.0, 25.0)
        assert (rate.cache_read, rate.cache_write) == (0.50, 6.25)

    def test_openai_56_family_write_premium(self) -> None:
        """Founder correction C1: GPT-5.6 family bills cache writes at 1.25x input."""
        terra = TABLE.rate("openai", "gpt-5.6-terra", date(2026, 6, 15))
        assert terra.cache_write == 3.125
        sol = TABLE.rate("openai", "gpt-5.6-sol", date(2026, 6, 15))
        assert sol.cache_write == 6.25

    def test_openai_54_family_no_write_premium(self) -> None:
        rate = TABLE.rate("openai", "gpt-5.4-mini", date(2026, 6, 15))
        assert rate.cache_write == rate.input  # zero write premium (non-5.6 families)

    def test_dated_snapshot_prefix_match(self) -> None:
        exact = TABLE.rate("anthropic", "claude-haiku-4-5", date(2026, 6, 20))
        dated = TABLE.rate("anthropic", "claude-haiku-4-5-20251001", date(2026, 6, 20))
        assert dated == exact

    def test_case_insensitive(self) -> None:
        assert TABLE.rate("Anthropic", "Claude-Opus-4-8", date(2026, 6, 15)).input == 5.0


class TestTPRC02EffectiveDateBoundaries:
    def test_sonnet5_intro_last_day(self) -> None:
        rate = TABLE.rate("anthropic", "claude-sonnet-5", date(2026, 8, 31))
        assert (rate.input, rate.output) == (2.0, 10.0)

    def test_sonnet5_standard_first_day(self) -> None:
        rate = TABLE.rate("anthropic", "claude-sonnet-5", date(2026, 9, 1))
        assert (rate.input, rate.output) == (3.0, 15.0)

    def test_date_before_coverage_raises(self) -> None:
        with pytest.raises(PricingGapError):
            TABLE.rate("anthropic", "claude-opus-4-8", date(2025, 1, 1))


class TestTPRC03UnknownModelPath:
    def test_unknown_model_raises_gap(self) -> None:
        with pytest.raises(PricingGapError, match="nonexistent/mystery-model"):
            TABLE.rate("nonexistent", "mystery-model", date(2026, 6, 15))

    def test_audit_continues_with_unpriced_listed(self) -> None:
        frame = make_frame(
            [
                {"prompt_tokens": 1000, "completion_tokens": 100},
                {"model": "mystery-9000", "prompt_tokens": 500, "completion_tokens": 50},
            ]
        )
        priced, unpriced = apply(TABLE, frame)
        assert unpriced == ["anthropic/mystery-9000"]
        assert priced["cost_usd"].isna().sum() == 1  # NaN, not silently zero
        assert priced["cost_usd"].notna().sum() == 1


class TestTPRC04GoldenValues:
    def test_golden_csv_exact(self) -> None:
        """Every golden row (independent spreadsheet arithmetic) matches the coster
        EXACTLY at float precision."""
        with (FIXTURES / "pricing_golden.csv").open() as fh:
            cases = list(csv.DictReader(fh))
        assert len(cases) == 13
        rows = [
            {
                "provider": c["provider"],
                "model": c["model"],
                "ts": datetime.fromisoformat(c["date"]).replace(tzinfo=UTC),
                "prompt_tokens": int(c["prompt_tokens"]),
                "cached_tokens": int(c["cached_tokens"]),
                "cache_write_tokens": int(c["cache_write_tokens"]),
                "completion_tokens": int(c["completion_tokens"]),
            }
            for c in cases
        ]
        priced, unpriced = apply(TABLE, make_frame(rows))
        assert unpriced == []
        for case, cost in zip(cases, priced["cost_usd"], strict=True):
            assert cost == pytest.approx(float(case["expected_cost_usd"]), abs=1e-12), (
                f"{case['case_id']}: got {cost!r}, spreadsheet says "
                f"{case['expected_cost_usd']} ({case['formula_note']})"
            )

    def test_negative_uncached_clipped(self) -> None:
        """Malformed row where cached+write exceeds prompt: uncached clips to 0."""
        frame = make_frame([{"prompt_tokens": 100, "cached_tokens": 200, "completion_tokens": 0}])
        priced, _ = apply(TABLE, frame)
        assert priced.loc[0, "cost_usd"] == pytest.approx(200 * 0.50 / 1e6)

    def test_empty_frame(self) -> None:
        empty = make_frame([{"prompt_tokens": 1}]).iloc[0:0]
        priced, unpriced = apply(TABLE, empty)
        assert len(priced) == 0
        assert unpriced == []
        reconcile(priced)  # zero-total, zero-parts: no raise


PRICED_MODELS = st.sampled_from(
    [
        ("anthropic", "claude-opus-4-8"),
        ("anthropic", "claude-sonnet-5"),
        ("anthropic", "claude-haiku-4-5"),
        ("openai", "gpt-5.6-terra"),
        ("openai", "gpt-5.4-nano"),
    ]
)

ROW = st.builds(
    lambda pm, prompt, cached_frac, write_frac, completion, day_offset: {
        "provider": pm[0],
        "model": pm[1],
        "prompt_tokens": prompt,
        "cached_tokens": int(prompt * cached_frac),
        "cache_write_tokens": 0 if pm[0] == "openai" else int(prompt * write_frac),
        "completion_tokens": completion,
        "ts": datetime(2026, 6, 10, 12, 0, tzinfo=UTC) + timedelta(days=day_offset),
    },
    pm=PRICED_MODELS,
    prompt=st.integers(min_value=0, max_value=2_000_000),
    cached_frac=st.floats(min_value=0, max_value=0.6),
    write_frac=st.floats(min_value=0, max_value=0.3),
    completion=st.integers(min_value=0, max_value=200_000),
    day_offset=st.integers(min_value=0, max_value=120),  # crosses the 2026-09-01 boundary
)


class TestTPRC05ReconcileProperty:
    @settings(max_examples=200, deadline=None)
    @given(rows=st.lists(ROW, min_size=1, max_size=60))
    def test_sum_of_parts_reconciles(self, rows: list[dict]) -> None:
        """NFR-07 property: for random frames, total == sum(by-model) == sum(by-day)
        within ±0.5%."""
        priced, unpriced = apply(TABLE, make_frame(rows))
        assert unpriced == []
        reconcile(priced)  # raises on violation

    def test_reconcile_detects_divergent_total(self) -> None:
        """A persisted headline total that disagrees with the parts must fail loudly."""
        frame = make_frame(
            [{"prompt_tokens": 10_000, "completion_tokens": 1_000} for _ in range(5)]
        )
        priced, _ = apply(TABLE, frame)
        good_total = total_spend(priced)
        reconcile(priced, total=good_total)  # exact figure passes
        reconcile(priced, total=good_total * 1.004)  # within ±0.5% passes
        with pytest.raises(ValueError, match="cost reconciliation failed"):
            reconcile(priced, total=good_total * 1.02)  # 2% off fails

    def test_reconcile_zero_total_with_nonzero_parts(self) -> None:
        frame = make_frame([{"prompt_tokens": 10_000, "completion_tokens": 1_000}])
        priced, _ = apply(TABLE, frame)
        with pytest.raises(ValueError, match="total is 0"):
            reconcile(priced, total=0.0)

    def test_unpriced_rows_excluded_consistently(self) -> None:
        frame = make_frame(
            [
                {"prompt_tokens": 10_000, "completion_tokens": 1_000},
                {"model": "mystery-9000", "prompt_tokens": 99_999, "completion_tokens": 9},
            ]
        )
        priced, unpriced = apply(TABLE, frame)
        assert unpriced == ["anthropic/mystery-9000"]
        reconcile(priced)  # NaN row excluded from total AND parts alike
