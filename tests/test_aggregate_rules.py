"""T-AGG-01..05: T2 aggregate estimators (PLAN-V15 R-Q1) — exact-value goldens
hand-derived in tests/fixtures/pricing_golden_NOTES.md (CLAUDE.md rule 4)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.rules.aggregate import (
    INACTIVE_ON_AGGREGATE,
    UPGRADE_PATH_LINE,
    run_aggregate_detectors,
)

FIXTURE = json.loads(Path("tests/fixtures/aggregate_usage.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def findings() -> list:
    frame = pd.DataFrame(FIXTURE["buckets"])
    frame["day"] = frame["day"].map(date.fromisoformat)
    return run_aggregate_detectors(
        frame,
        FIXTURE["provider"],
        PricingTable.load(),
        Settings(secret_key="x" * 64, database_url="sqlite://", _env_file=None),
        FIXTURE["observed_days"],
    )


def by_detector_model(findings: list) -> dict[tuple[str, str], float]:
    return {
        (f.detector, str(f.detail["model"])): round(f.monthly_cost_impact_usd, 4) for f in findings
    }


class TestAggregateGoldens:
    def test_01_d1_exact(self, findings: list) -> None:
        got = by_detector_model(findings)
        # NOTES derivation: window 4.455 (3.15 + 1.305) x 30/10 = 13.365
        assert got[("d1_oversized_model", "claude-opus-4-8")] == 13.365

    def test_02_d2_exact(self, findings: list) -> None:
        got = by_detector_model(findings)
        # sonnet: 1,000,000 extra-cached x (2.0-0.2)/1e6 x 0.8 x 3 = 4.32
        assert got[("d2_missing_cache", "claude-sonnet-5")] == 4.32
        # opus: 200,000 x (5.0-0.5)/1e6 x 0.8 x 3 = 2.16
        assert got[("d2_missing_cache", "claude-opus-4-8")] == 2.16
        # haiku: 600,000 x (1.0-0.1)/1e6 x 0.8 x 3 = 1.296
        assert got[("d2_missing_cache", "claude-haiku-4-5-20251001")] == 1.296

    def test_03_d3_exact(self, findings: list) -> None:
        got = by_detector_model(findings)
        # haiku bucket H: 1,500,000 excess x 0.82/1e6 x 3 = 3.69
        assert got[("d3_prompt_bloat", "claude-haiku-4-5-20251001")] == 3.69

    def test_04_exactly_five_findings_all_estimated(self, findings: list) -> None:
        assert len(findings) == 5
        assert all(f.confidence == "estimated" for f in findings)
        assert [round(f.monthly_cost_impact_usd, 4) for f in findings] == sorted(
            (round(f.monthly_cost_impact_usd, 4) for f in findings), reverse=True
        )

    def test_05_inactive_set_never_emits(self, findings: list) -> None:
        # R-Q1 law: no savings number from a detector the tier cannot support
        emitted = {f.detector for f in findings}
        assert emitted.isdisjoint(INACTIVE_ON_AGGREGATE)
        assert INACTIVE_ON_AGGREGATE == (
            "d4_retry_storm",
            "d5_unbounded_max_tokens",
            "d6_chatty_loop",
        )
        assert "per-request logs" in UPGRADE_PATH_LINE


class TestAggregateFR22:
    def test_evidence_counts_only(self, findings: list) -> None:
        for f in findings:
            for ev in f.evidence:
                assert set(ev.__dataclass_fields__) == {"row_idx", "ts", "model", "tokens", "note"}
                assert ev.note == "aggregate-bucket"


class TestAggregateFalsePositiveGuard:
    """T-AGG-06 (G-V1 vv f.4): empty and clean frames emit NOTHING."""

    def test_06_empty_and_clean_frames(self) -> None:
        settings = Settings(secret_key="x" * 64, database_url="sqlite://", _env_file=None)
        table = PricingTable.load()
        empty = pd.DataFrame(
            columns=["day", "model", "calls", "prompt_tokens", "completion_tokens", "cached_tokens"]
        )
        assert run_aggregate_detectors(empty, "anthropic", table, settings, 1) == []
        # Clean: unmapped-eligible traffic — long completions (no d1), zero
        # caching anywhere (no d2 target to extend), identical prompt sizes
        # across >=3 buckets (no d3 bloat).
        clean = pd.DataFrame(
            [
                {
                    "day": date(2026, 7, d),
                    "model": "claude-haiku-4-5-20251001",
                    "calls": 100,
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 50_000,
                    "cached_tokens": 0,
                }
                for d in (1, 2, 3, 4)
            ]
        )
        assert run_aggregate_detectors(clean, "anthropic", table, settings, 4) == []

    def test_07_effective_prompt_rate_zero_prompt_guard(self) -> None:
        # findings.py zero-prompt branch (money-math 100% gate, vv f.2)
        from datetime import date as date_cls

        from tokenops_cost_auditor.services.rules.findings import effective_prompt_rate

        rate = PricingTable.load().rate("anthropic", "claude-sonnet-5", date_cls(2026, 7, 10))
        row = pd.Series({"prompt_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0})
        assert effective_prompt_rate(row, rate) == rate.input
