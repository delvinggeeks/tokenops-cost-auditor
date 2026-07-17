"""D4 rules tests — T-RUL-00, T-RUL-EV-01, T-RUL-D2-01..03, T-RUL-D4-01..02.

Golden values derived independently in tests/fixtures/pricing_golden_NOTES.md
(waste_pack v1 section)."""

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.ingest import load
from tokenops_cost_auditor.services.pricing.coster import apply
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.rules import d2_missing_cache as d2mod
from tokenops_cost_auditor.services.rules.base import DetectorContext, ttl_window_s
from tokenops_cost_auditor.services.rules.d2_missing_cache import D2MissingCache
from tokenops_cost_auditor.services.rules.d4_retry_storm import D4RetryStorm
from tokenops_cost_auditor.services.rules.findings import (
    Confidence,
    EvidenceRef,
    Finding,
    Severity,
    make_evidence,
    monthly_factor,
    observed_days,
    severity_for_impact,
)
from tokenops_cost_auditor.services.rules.registry import DETECTORS, run_all

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = PricingTable.load()

# Independently derived goldens (pricing_golden_NOTES.md, waste_pack v1 section)
D2_GOLDEN_MONTHLY = 0.246784
D4_GOLDEN_MONTHLY = 0.0510


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def priced_fixture(*names: str) -> pd.DataFrame:
    frames = []
    for name in names:
        frame, report = load(FIXTURES / name)
        assert report.valid_pct == 100.0
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    priced, unpriced = apply(TABLE, combined)
    assert unpriced == []
    return priced


def ctx_for(frame: pd.DataFrame, settings: Settings | None = None) -> DetectorContext:
    return DetectorContext(
        settings=settings or make_settings(),
        table=TABLE,
        observed_days=observed_days(frame),
    )


@pytest.fixture(scope="module")
def waste_pack() -> pd.DataFrame:
    return priced_fixture("waste_pack_anthropic.jsonl", "waste_pack_openai.jsonl")


@pytest.fixture(scope="module")
def clean_optimal() -> pd.DataFrame:
    return priced_fixture("clean_optimal.jsonl")


def synth_frame(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "ts": datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
        "prompt_tokens": 2000,
        "completion_tokens": 100,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "tag": "t",
        "prefix_hash": "h" * 64,
        "endpoint": "",
        "request_id": "r",
    }
    frame = pd.DataFrame([{**defaults, **row} for row in rows])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    priced, _ = apply(TABLE, frame)
    return priced


class TestTRUL00Registry:
    def test_runs_all_ordered_by_impact_stable(self, waste_pack: pd.DataFrame) -> None:
        first = run_all(waste_pack, ctx_for(waste_pack))
        second = run_all(waste_pack, ctx_for(waste_pack))
        assert [f.id for f in first] == [f.id for f in second]  # stable
        impacts = [f.monthly_cost_impact_usd for f in first]
        assert impacts == sorted(impacts, reverse=True)  # ranked by $ (FR-13)
        assert {f.detector for f in first} == {"d2_missing_cache", "d4_retry_storm"}

    def test_disable_flag(self, waste_pack: pd.DataFrame) -> None:
        settings = make_settings(rules_disabled=["d2_missing_cache"])
        findings = run_all(waste_pack, ctx_for(waste_pack, settings))
        assert findings, "d4 must still run"
        assert all(f.detector == "d4_retry_storm" for f in findings)

    def test_registry_order_is_declared_order(self) -> None:
        assert [d.name for d in DETECTORS] == ["d2_missing_cache", "d4_retry_storm"]


class TestTRULEV01Evidence:
    def test_evidence_capped_and_text_free(self, waste_pack: pd.DataFrame) -> None:
        findings = run_all(waste_pack, ctx_for(waste_pack))
        assert findings
        for f in findings:
            assert len(f.evidence) <= 20
            for ref in f.evidence:
                assert set(dataclasses.asdict(ref)) == {
                    "row_idx",
                    "ts",
                    "model",
                    "tokens",
                    "note",
                }
            # FR-22: no prompt/completion text anywhere in the finding
            blob = repr(f)
            assert "CACHE-ME" not in blob
            assert "RETRY-ME" not in blob

    def test_finding_rejects_oversized_evidence(self) -> None:
        refs = tuple(
            EvidenceRef(row_idx=i, ts="2026-06-10T00:00:00+00:00", model="m", tokens=1, note="n")
            for i in range(21)
        )
        with pytest.raises(ValueError, match="evidence exceeds 20"):
            Finding(
                id="X-001",
                detector="x",
                severity=Severity.LOW,
                monthly_cost_impact_usd=0.0,
                confidence=Confidence.ESTIMATED,
                fix_text="f",
                evidence=refs,
            )

    def test_estimator_helpers(self) -> None:
        assert observed_days(pd.DataFrame()) == 1
        assert monthly_factor(0) == 30.0
        assert monthly_factor(30) == 1.0
        assert severity_for_impact(500.0) is Severity.HIGH
        assert severity_for_impact(50.0) is Severity.MED
        assert severity_for_impact(49.99) is Severity.LOW
        frame = synth_frame([{} for _ in range(25)])
        refs = make_evidence(frame, note="n", limit=3)
        assert len(refs) == 3


class TestTRULD2:
    def test_01_golden_on_waste_pack(self, waste_pack: pd.DataFrame) -> None:
        findings = D2MissingCache().run(waste_pack, ctx_for(waste_pack))
        assert len(findings) == 1
        f = findings[0]
        assert f.monthly_cost_impact_usd == pytest.approx(D2_GOLDEN_MONTHLY, abs=1e-12)
        assert f.confidence is Confidence.CONSERVATIVE  # hash-based
        assert f.severity is Severity.LOW
        assert "claude-sonnet-5" in f.fix_text
        assert 1 <= len(f.evidence) <= 20

    def test_02_silent_on_clean_optimal(self, clean_optimal: pd.DataFrame) -> None:
        assert D2MissingCache().run(clean_optimal, ctx_for(clean_optimal)) == []

    def test_03_repeat_threshold_boundary(self) -> None:
        def bucket(n: int) -> pd.DataFrame:
            base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
            return synth_frame(
                [{"ts": base + timedelta(seconds=20 * i), "request_id": f"r{i}"} for i in range(n)]
            )

        below = D2MissingCache().run(bucket(24), ctx_for(bucket(24)))
        assert below == []  # 24 < CACHE_MIN_REPEATS
        at = D2MissingCache().run(bucket(25), ctx_for(bucket(25)))
        assert len(at) == 1

    def test_03_min_prompt_boundary(self) -> None:
        def bucket(prompt: int) -> pd.DataFrame:
            base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
            return synth_frame(
                [
                    {"ts": base + timedelta(seconds=20 * i), "prompt_tokens": prompt}
                    for i in range(25)
                ]
            )

        assert D2MissingCache().run(bucket(1023), ctx_for(bucket(1023))) == []
        assert len(D2MissingCache().run(bucket(1024), ctx_for(bucket(1024)))) == 1

    def test_03_heuristic_bucket_estimated_confidence(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        frame = synth_frame(
            [{"ts": base + timedelta(seconds=20 * i), "prefix_hash": None} for i in range(25)]
        )
        findings = D2MissingCache().run(frame, ctx_for(frame))
        assert len(findings) == 1
        assert findings[0].confidence is Confidence.ESTIMATED  # no hash evidence
        assert "size-matched estimate" in findings[0].fix_text

    def test_03_no_window_haircut_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """R-Q4: windows not estimable -> est_writes=1 and 0.7 haircut."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        frame = synth_frame([{"ts": base + timedelta(seconds=20 * i)} for i in range(25)])
        normal = D2MissingCache().run(frame, ctx_for(frame))[0]
        monkeypatch.setattr(d2mod, "_estimate_writes", lambda bucket, ttl: None)
        haircut = D2MissingCache().run(frame, ctx_for(frame))[0]
        # haiku rates: input 1, read 0.10, write 1.25; cacheable = 1024
        expected = 0.7 * ((25 - 1) * 1024 * 0.9 - 1 * 1024 * 0.25) / 1e6 * 30.0
        assert haircut.monthly_cost_impact_usd == pytest.approx(expected, abs=1e-12)
        assert haircut.monthly_cost_impact_usd != normal.monthly_cost_impact_usd

    def test_estimate_writes_none_on_all_nat(self) -> None:
        frame = pd.DataFrame({"ts": pd.to_datetime([pd.NaT, pd.NaT], utc=True)})
        assert d2mod._estimate_writes(frame, 300) is None

    def test_ttl_per_provider_family(self) -> None:
        s = make_settings()
        assert ttl_window_s(s, "anthropic", "claude-sonnet-5") == 300
        assert ttl_window_s(s, "openai", "gpt-5.6-terra") == 1800  # correction C4
        assert ttl_window_s(s, "openai", "gpt-5.4-mini") == 300  # fallback


class TestTRULD4:
    def test_01_golden_on_waste_pack(self, waste_pack: pd.DataFrame) -> None:
        findings = D4RetryStorm().run(waste_pack, ctx_for(waste_pack))
        assert len(findings) == 1
        f = findings[0]
        assert f.monthly_cost_impact_usd == pytest.approx(D4_GOLDEN_MONTHLY, abs=1e-12)
        assert f.severity is Severity.MED  # largest cluster 5 < 10
        assert f.confidence is Confidence.CONSERVATIVE
        assert "support-bot" in f.fix_text

    def test_01_high_severity_at_10(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        frame = synth_frame(
            [{"ts": base + timedelta(seconds=5 * i), "request_id": f"r{i}"} for i in range(10)]
        )
        findings = D4RetryStorm().run(frame, ctx_for(frame))
        assert len(findings) == 1
        assert findings[0].severity is Severity.HIGH

    def test_02_silent_on_clean_optimal(self, clean_optimal: pd.DataFrame) -> None:
        assert D4RetryStorm().run(clean_optimal, ctx_for(clean_optimal)) == []

    def test_02_dup_min_boundary(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

        def frame(n: int) -> pd.DataFrame:
            return synth_frame(
                [{"ts": base + timedelta(seconds=10 * i), "request_id": f"r{i}"} for i in range(n)]
            )

        assert D4RetryStorm().run(frame(2), ctx_for(frame(2))) == []
        assert len(D4RetryStorm().run(frame(3), ctx_for(frame(3)))) == 1

    def test_02_window_anchor_boundary(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        inside = synth_frame([{"ts": base + timedelta(seconds=t)} for t in (0, 60, 120)])
        assert len(D4RetryStorm().run(inside, ctx_for(inside))) == 1
        split = synth_frame([{"ts": base + timedelta(seconds=t)} for t in (0, 60, 121)])
        assert D4RetryStorm().run(split, ctx_for(split)) == []  # 121s exceeds anchor window
