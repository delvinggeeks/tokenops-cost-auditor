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
        assert {f.detector for f in first} == {
            "d1_oversized_model",
            "d2_missing_cache",
            "d3_prompt_bloat",
            "d4_retry_storm",
            "d5_unbounded_max_tokens",
            "d6_chatty_loop",
        }

    def test_disable_flag(self, waste_pack: pd.DataFrame) -> None:
        settings = make_settings(rules_disabled=["d2_missing_cache"])
        findings = run_all(waste_pack, ctx_for(waste_pack, settings))
        detectors = {f.detector for f in findings}
        assert "d2_missing_cache" not in detectors
        assert "d4_retry_storm" in detectors  # others still run

    def test_registry_order_is_declared_order(self) -> None:
        assert [d.name for d in DETECTORS] == [
            "d1_oversized_model",
            "d2_missing_cache",
            "d3_prompt_bloat",
            "d4_retry_storm",
            "d5_unbounded_max_tokens",
            "d6_chatty_loop",
        ]


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
            for marker in ("CACHE-ME", "RETRY-ME", "D1-UNIQUE", "D3-rag", "D6-REREAD", "D5-UNIQUE"):
                assert marker not in blob, marker

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
        monkeypatch.setattr(d2mod, "_window_ids", lambda bucket, ttl: None)
        haircut = D2MissingCache().run(frame, ctx_for(frame))[0]
        # haiku rates: input 1, read 0.10, write 1.25; cacheable = 1024
        expected = 0.7 * ((25 - 1) * 1024 * 0.9 - 1 * 1024 * 0.25) / 1e6 * 30.0
        assert haircut.monthly_cost_impact_usd == pytest.approx(expected, abs=1e-12)
        assert haircut.monthly_cost_impact_usd != normal.monthly_cost_impact_usd

    def test_window_ids_none_on_all_nat(self) -> None:
        frame = pd.DataFrame({"ts": pd.to_datetime([pd.NaT, pd.NaT], utc=True)})
        assert d2mod._window_ids(frame, 300) is None

    def test_window_ids_tz_naive_assumed_utc(self) -> None:
        """G3 cold-reviewer f.4: tz-naive timestamps must not crash the detector."""
        frame = pd.DataFrame({"ts": pd.to_datetime(["2026-06-10 09:00:00", "2026-06-10 09:10:00"])})
        ids = d2mod._window_ids(frame, 300)
        assert ids is not None
        assert ids.nunique() == 2

    def test_rate_boundary_spanning_bucket_repriced_per_day(self) -> None:
        """G3 cold-reviewer f.1: a bucket straddling the Sonnet-5 Sep-1 boundary
        must price each day at its own card. Expected value independently derived:
        25 calls/day at 20s spacing (span 480s = 2 TTL windows/day, writes = first
        call of each window, reads = 23/day), cacheable = min(2000, 1024) = 1024:
          Aug 31 (intro 2/0.20/2.50): 23x1.8 - 2x0.5  = 40.4 x 1024/1e6 = 0.0413696
          Sep 01 (std   3/0.30/3.75): 23x2.7 - 2x0.75 = 60.6 x 1024/1e6 = 0.0620544
        observed 0.103424; observed_days=2 -> monthly x15 = 1.55136."""
        rows = []
        days = (datetime(2026, 8, 31, 0, 0, tzinfo=UTC), datetime(2026, 9, 1, 0, 0, tzinfo=UTC))
        for day in days:
            rows.extend(
                {
                    "model": "claude-sonnet-5",
                    "ts": day + timedelta(seconds=20 * i),
                    "prompt_tokens": 2000,
                    "completion_tokens": 400,
                    "request_id": f"r-{day.day}-{i}",
                }
                for i in range(25)
            )
        frame = synth_frame(rows)
        findings = D2MissingCache().run(frame, ctx_for(frame))
        assert len(findings) == 1
        assert findings[0].monthly_cost_impact_usd == pytest.approx(1.55136, abs=1e-12)

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


class TestEffectivePromptRateUATFix:
    """UAT-1 mini-milestone (D11): prompt-token savings priced as billed —
    cache reads at cache_read rates, never flat input rate."""

    def test_uncached_rows_equal_input_rate(self) -> None:
        """Goldens invariant by construction: no cache activity -> input rate."""
        from tokenops_cost_auditor.services.rules.findings import effective_prompt_rate

        frame = synth_frame([{"prompt_tokens": 2000, "cached_tokens": 0}])
        rate = TABLE.rate("anthropic", "claude-haiku-4-5", frame["ts"].iloc[0].date())
        assert effective_prompt_rate(frame.iloc[0], rate) == rate.input

    def test_cache_read_heavy_rows_price_near_read_rate(self) -> None:
        from tokenops_cost_auditor.services.rules.findings import effective_prompt_rate

        frame = synth_frame([{"prompt_tokens": 28000, "cached_tokens": 27000}])
        rate = TABLE.rate("anthropic", "claude-haiku-4-5", frame["ts"].iloc[0].date())
        eff = effective_prompt_rate(frame.iloc[0], rate)
        blend = (1000 * rate.input + 27000 * rate.cache_read) / 28000
        assert abs(eff - blend) < 1e-12
        assert eff < rate.input / 2  # cache-heavy rows are far below input rate

    def test_d6_agent_session_savings_shrink_with_cache(self) -> None:
        """The same chatty run, cached vs uncached: cached savings must be a
        small fraction (the 228%-savings dogfood defect)."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

        def run_frame(cached: int) -> pd.DataFrame:
            return synth_frame(
                [
                    {
                        "ts": base + timedelta(seconds=30 * i),
                        "request_id": f"r{i}",
                        "prompt_tokens": 28000,
                        "cached_tokens": cached,
                        "completion_tokens": 80,
                        "prefix_hash": "h" * 64,
                    }
                    for i in range(10)
                ]
            )

        uncached = run_frame(0)
        cached = run_frame(27000)
        f_uncached = D6ChattyLoop().run(uncached, ctx_for(uncached))
        f_cached = D6ChattyLoop().run(cached, ctx_for(cached))
        assert len(f_uncached) == 1 and len(f_cached) == 1
        ratio = f_cached[0].monthly_cost_impact_usd / f_uncached[0].monthly_cost_impact_usd
        assert ratio < 0.2  # cache-read pricing collapses the over-claim


class TestD4UATDogfoodFixes:
    """UAT-1 mini-milestone (D11): agent-session traffic must not read as storms."""

    def test_cache_active_rows_excluded(self) -> None:
        """Cache-stable agent steps (identical shapes, seconds apart, cache reads
        on every call) are session continuations, not retry storms."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        agent_session = synth_frame(
            [
                {
                    "ts": base + timedelta(seconds=8 * i),
                    "request_id": f"r{i}",
                    "prompt_tokens": 28190,
                    "cached_tokens": 28000,
                    "completion_tokens": 40,
                }
                for i in range(12)
            ]
        )
        assert D4RetryStorm().run(agent_session, ctx_for(agent_session)) == []

    def test_cache_writes_also_excluded(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        writes = synth_frame(
            [
                {
                    "ts": base + timedelta(seconds=8 * i),
                    "request_id": f"r{i}",
                    "prompt_tokens": 28190,
                    "cache_write_tokens": 28000,
                }
                for i in range(5)
            ]
        )
        assert D4RetryStorm().run(writes, ctx_for(writes)) == []

    def test_unhashed_fingerprint_includes_completion(self) -> None:
        """Same prompt size but different completions = different work, not
        duplicates (prompt-only fingerprints collided on real agent traffic)."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        varied = synth_frame(
            [
                {
                    "ts": base + timedelta(seconds=10 * i),
                    "request_id": f"r{i}",
                    "prefix_hash": None,
                    "completion_tokens": 100 + i,  # all different
                }
                for i in range(6)
            ]
        )
        assert D4RetryStorm().run(varied, ctx_for(varied)) == []
        identical = synth_frame(
            [
                {
                    "ts": base + timedelta(seconds=10 * i),
                    "request_id": f"r{i}",
                    "prefix_hash": None,
                    "completion_tokens": 100,  # identical shape -> still caught
                }
                for i in range(6)
            ]
        )
        assert len(D4RetryStorm().run(identical, ctx_for(identical))) == 1


# --- D5-milestone detectors (goldens from pricing_golden_NOTES.md, waste_pack v2) ---

from tokenops_cost_auditor.services.rules.d1_oversized_model import (  # noqa: E402
    QUALITY_CAVEAT,
    D1OversizedModel,
)
from tokenops_cost_auditor.services.rules.d3_prompt_bloat import D3PromptBloat  # noqa: E402
from tokenops_cost_auditor.services.rules.d5_unbounded_max_tokens import (  # noqa: E402
    D5UnboundedMaxTokens,
)
from tokenops_cost_auditor.services.rules.d6_chatty_loop import D6ChattyLoop  # noqa: E402

D1_GOLDEN_MONTHLY = 1.35
D3_GOLDEN_MONTHLY = 0.50
D6_GOLDEN_MONTHLY = 0.096


class TestTRULD1:
    def test_01_golden_on_waste_pack(self, waste_pack: pd.DataFrame) -> None:
        findings = D1OversizedModel().run(waste_pack, ctx_for(waste_pack))
        assert len(findings) == 1
        f = findings[0]
        assert f.monthly_cost_impact_usd == pytest.approx(D1_GOLDEN_MONTHLY, abs=1e-12)
        assert f.confidence is Confidence.ESTIMATED  # R-D1-MAP(c)
        assert QUALITY_CAVEAT in f.fix_text  # R-D1-MAP(e)
        assert "claude-sonnet-5" in f.fix_text  # one tier down, same provider

    def test_02_silent_on_clean_optimal(self, clean_optimal: pd.DataFrame) -> None:
        assert D1OversizedModel().run(clean_optimal, ctx_for(clean_optimal)) == []

    def test_03_p50_threshold_boundary(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

        def bucket(completion: int) -> pd.DataFrame:
            return synth_frame(
                [
                    {
                        "model": "claude-opus-4-8",
                        "ts": base + timedelta(seconds=400 * i),
                        "prompt_tokens": 500,
                        "completion_tokens": completion,
                        "prefix_hash": f"u{i}" * 32,
                    }
                    for i in range(10)
                ]
            )

        at = bucket(150)  # p50 == threshold: NOT below -> silent
        assert D1OversizedModel().run(at, ctx_for(at)) == []
        below = bucket(149)
        assert len(D1OversizedModel().run(below, ctx_for(below))) == 1

    def test_03_unmapped_frontier_informational(self) -> None:
        """R-D1-MAP(f): frontier without a map entry -> informational, no savings."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        frame = synth_frame(
            [
                {
                    "model": "claude-haiku-4-5",
                    "ts": base + timedelta(seconds=400 * i),
                    "completion_tokens": 50,
                    "prefix_hash": f"u{i}" * 32,
                }
                for i in range(5)
            ]
        )
        settings = make_settings(d1_frontier_models=["claude-haiku-4-5"])
        findings = D1OversizedModel().run(frame, ctx_for(frame, settings))
        assert len(findings) == 1
        assert findings[0].id.startswith("D1-INFO-")
        assert findings[0].monthly_cost_impact_usd == 0.0
        assert QUALITY_CAVEAT in findings[0].fix_text

    def test_03_sibling_models_never_bleed(self) -> None:
        """Boundary rule: gpt-5.4-nano must not match the gpt-5.4 map key."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        frame = synth_frame(
            [
                {
                    "provider": "openai",
                    "model": "gpt-5.4-nano",
                    "ts": base + timedelta(seconds=400 * i),
                    "completion_tokens": 30,
                    "prefix_hash": f"u{i}" * 32,
                }
                for i in range(5)
            ]
        )
        assert D1OversizedModel().run(frame, ctx_for(frame)) == []

    def test_03_cached_bucket_excluded(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        frame = synth_frame(
            [
                {
                    "model": "claude-opus-4-8",
                    "ts": base + timedelta(seconds=400 * i),
                    "completion_tokens": 50,
                    "cached_tokens": 800,
                    "prefix_hash": f"u{i}" * 32,
                }
                for i in range(5)
            ]
        )
        assert D1OversizedModel().run(frame, ctx_for(frame)) == []


class TestTRULD3:
    def test_01_golden_on_waste_pack(self, waste_pack: pd.DataFrame) -> None:
        findings = D3PromptBloat().run(waste_pack, ctx_for(waste_pack))
        assert len(findings) == 1
        f = findings[0]
        assert f.monthly_cost_impact_usd == pytest.approx(D3_GOLDEN_MONTHLY, abs=1e-12)
        assert f.confidence is Confidence.ESTIMATED
        assert "rag-bloated" in f.fix_text

    def test_02_silent_on_clean_optimal(self, clean_optimal: pd.DataFrame) -> None:
        assert D3PromptBloat().run(clean_optimal, ctx_for(clean_optimal)) == []

    def test_02_multiplier_boundary(self) -> None:
        """p90 exactly at mult x median must NOT fire; just above must."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

        def frame(bloated_prompt: int) -> pd.DataFrame:
            rows = [
                {
                    "tag": "lean",
                    "ts": base + timedelta(seconds=400 * i),
                    "prompt_tokens": 1000,
                    "completion_tokens": 350,
                    "prefix_hash": f"l{i}" * 32,
                }
                for i in range(30)
            ] + [
                {
                    "tag": "fat",
                    "ts": base + timedelta(seconds=400 * i + 50),
                    "prompt_tokens": bloated_prompt,
                    "completion_tokens": 350,
                    "prefix_hash": f"f{i}" * 32,
                }
                for i in range(10)
            ]
            return synth_frame(rows)

        at = frame(2000)  # corpus median 1000; p90 2000 == 2.0x -> silent
        assert D3PromptBloat().run(at, ctx_for(at)) == []
        above = frame(2001)
        findings = D3PromptBloat().run(above, ctx_for(above))
        assert len(findings) == 1
        assert "fat" in findings[0].fix_text


class TestTRULD5:
    def test_01_informational_on_waste_pack(self, waste_pack: pd.DataFrame) -> None:
        findings = D5UnboundedMaxTokens().run(waste_pack, ctx_for(waste_pack))
        assert len(findings) == 1
        f = findings[0]
        assert f.monthly_cost_impact_usd == 0.0  # informational (LLD; flag off)
        assert f.severity is Severity.LOW
        assert "generator" in f.fix_text
        assert "8192" in f.fix_text

    def test_02_silent_on_clean_optimal(self, clean_optimal: pd.DataFrame) -> None:
        assert D5UnboundedMaxTokens().run(clean_optimal, ctx_for(clean_optimal)) == []

    def test_02_ratio_boundary_and_missing_max(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

        def frame(declared: float | None) -> pd.DataFrame:
            return synth_frame(
                [
                    {
                        "ts": base + timedelta(seconds=400 * i),
                        "completion_tokens": 100,
                        "declared_max_tokens": declared,
                        "prefix_hash": f"u{i}" * 32,
                    }
                    for i in range(5)
                ]
            )

        below = frame(399.0)  # < 4 x p95(100)
        assert D5UnboundedMaxTokens().run(below, ctx_for(below)) == []
        at = frame(400.0)  # >= 4x fires
        assert len(D5UnboundedMaxTokens().run(at, ctx_for(at))) == 1
        absent = frame(None)  # no declared max in logs -> nothing to flag
        assert D5UnboundedMaxTokens().run(absent, ctx_for(absent)) == []


class TestTRULD6:
    def test_01_golden_on_waste_pack(self, waste_pack: pd.DataFrame) -> None:
        findings = D6ChattyLoop().run(waste_pack, ctx_for(waste_pack))
        assert len(findings) == 1
        f = findings[0]
        assert f.monthly_cost_impact_usd == pytest.approx(D6_GOLDEN_MONTHLY, abs=1e-12)
        assert "Agent loop suspected" in f.fix_text  # re-read signature fired
        assert "agent-7" in f.fix_text

    def test_02_silent_on_clean_optimal(self, clean_optimal: pd.DataFrame) -> None:
        assert D6ChattyLoop().run(clean_optimal, ctx_for(clean_optimal)) == []

    def test_03_loop_min_boundary(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

        def frame(n: int) -> pd.DataFrame:
            return synth_frame(
                [
                    {
                        "tag": "loop",
                        "ts": base + timedelta(seconds=30 * i),
                        "prompt_tokens": 1000,
                        "completion_tokens": 50,
                        "prefix_hash": f"u{i}" * 32,
                    }
                    for i in range(n)
                ]
            )

        seven = frame(7)
        assert D6ChattyLoop().run(seven, ctx_for(seven)) == []
        eight = frame(8)
        findings = D6ChattyLoop().run(eight, ctx_for(eight))
        assert len(findings) == 1
        assert "Agent loop suspected" not in findings[0].fix_text  # unique hashes

    def test_03_session_gap_splits(self) -> None:
        """A 15-min gap splits sessions; two runs of 5 small calls never fire."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        rows = []
        for half in range(2):
            start = base + timedelta(seconds=half * 2000)  # gap 2000s > 900s
            rows.extend(
                {
                    "tag": "loop",
                    "ts": start + timedelta(seconds=30 * i),
                    "prompt_tokens": 1000,
                    "completion_tokens": 50,
                    "prefix_hash": f"h{half}-{i}" * 16,
                }
                for i in range(5)
            )
        frame = synth_frame(rows)
        assert D6ChattyLoop().run(frame, ctx_for(frame)) == []
