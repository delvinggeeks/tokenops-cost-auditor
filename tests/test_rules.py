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
from tokenops_cost_auditor.services.rules.d8_spend_concentration import D8SpendConcentration
from tokenops_cost_auditor.services.rules.d9_ineffective_cache import D9IneffectiveCache
from tokenops_cost_auditor.services.rules.d10_spend_anomaly import D10SpendAnomaly
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


@pytest.mark.verifies_requirement("FR-13")
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
            "d8_spend_concentration",
            "d9_ineffective_cache",
            "d10_spend_anomaly",
        ]


@pytest.mark.verifies_requirement("FR-13")
@pytest.mark.verifies_requirement("FR-22")
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


@pytest.mark.verifies_requirement("FR-08")
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


@pytest.mark.verifies_requirement("FR-10")
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
        # distinct request_ids: three separate calls (UAT-D5: shared id = one call)
        inside = synth_frame(
            [{"ts": base + timedelta(seconds=t), "request_id": f"r{t}"} for t in (0, 60, 120)]
        )
        assert len(D4RetryStorm().run(inside, ctx_for(inside))) == 1
        split = synth_frame(
            [{"ts": base + timedelta(seconds=t), "request_id": f"r{t}"} for t in (0, 60, 121)]
        )
        assert D4RetryStorm().run(split, ctx_for(split)) == []  # 121s exceeds anchor window

    def test_02_shared_request_id_never_a_storm(self) -> None:
        """UAT-D5: logger echoes of ONE call (same request_id) are not retries."""
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        echoes = synth_frame(
            [{"ts": base + timedelta(seconds=10 * i), "request_id": "msg_same"} for i in range(6)]
        )
        assert D4RetryStorm().run(echoes, ctx_for(echoes)) == []


@pytest.mark.verifies_requirement("FR-10")
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


@pytest.mark.verifies_requirement("FR-10")
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


@pytest.mark.verifies_requirement("FR-07")
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


@pytest.mark.verifies_requirement("FR-09")
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


@pytest.mark.verifies_requirement("FR-11")
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


@pytest.mark.verifies_requirement("FR-12")
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


@pytest.mark.verifies_requirement("FR-12")
class TestRD6AGGSessionAggregation:
    """R-D6-AGG (founder 2026-07-18): one finding per session for D6 and D4."""

    def test_d6_two_runs_one_session_one_finding_summed(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        # two qualifying runs separated by 700s (> run window 600, < session gap 900)
        rows = [
            {"ts": base + timedelta(seconds=30 * i), "request_id": f"a{i}", "completion_tokens": 80}
            for i in range(10)
        ] + [
            {
                "ts": base + timedelta(seconds=1000 + 30 * i),
                "request_id": f"b{i}",
                "completion_tokens": 80,
            }
            for i in range(10)
        ]
        frame = synth_frame(rows)
        findings = D6ChattyLoop().run(frame, ctx_for(frame))
        assert len(findings) == 1  # one session -> ONE finding
        detail = findings[0].detail
        assert detail is not None and len(detail["runs"]) == 2  # per-run breakdown kept
        run_sum = sum(r["observed_savings_usd"] for r in detail["runs"])
        factor = 30.0  # single-day frame
        assert abs(findings[0].monthly_cost_impact_usd - run_sum * factor) < 1e-9
        assert "2 burst(s)" in findings[0].fix_text  # run count stated (R-D6-AGG)
        # evidence sampled ACROSS runs, capped at 20
        assert len(findings[0].evidence) <= 20
        evidence_ts = {e.ts for e in findings[0].evidence}
        first_run_ts = {(base + timedelta(seconds=30 * i)).isoformat() for i in range(10)}
        assert evidence_ts - first_run_ts  # at least one ref from the second run

    def test_d6_separate_sessions_stay_separate(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        rows = [
            {"ts": base + timedelta(seconds=30 * i), "request_id": f"a{i}", "completion_tokens": 80}
            for i in range(10)
        ] + [
            {
                "ts": base + timedelta(seconds=3000 + 30 * i),  # 2100s gap > 900s
                "request_id": f"b{i}",
                "completion_tokens": 80,
            }
            for i in range(10)
        ]
        frame = synth_frame(rows)
        assert len(D6ChattyLoop().run(frame, ctx_for(frame))) == 2

    def test_d4_two_clusters_one_session_one_finding(self) -> None:
        base = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
        # two identical-call bursts 400s apart (same session, separate anchors)
        rows = [
            {"ts": base + timedelta(seconds=10 * i), "request_id": f"a{i}"} for i in range(4)
        ] + [
            {"ts": base + timedelta(seconds=400 + 10 * i), "request_id": f"b{i}"} for i in range(4)
        ]
        frame = synth_frame(rows)
        findings = D4RetryStorm().run(frame, ctx_for(frame))
        assert len(findings) == 1
        detail = findings[0].detail
        assert detail is not None and len(detail["clusters"]) == 2
        assert "2 burst(s) in one session" in findings[0].fix_text


@pytest.mark.verifies_requirement("FR-33")
class TestD8SpendConcentration:
    """D8 — informational 'start here' pointer (founder 2026-07-25). Flags the
    route that carries a large share of spend; never claims a saving."""

    def test_flags_the_dominant_route_as_informational(self) -> None:
        frame = synth_frame(
            [
                {"tag": "chat", "prompt_tokens": 1_000_000, "completion_tokens": 1000},
                {"tag": "chat", "prompt_tokens": 1_000_000, "completion_tokens": 1000},
                {"tag": "batch", "prompt_tokens": 1000, "completion_tokens": 10},
            ]
        )
        findings = D8SpendConcentration().run(frame, ctx_for(frame))
        assert len(findings) == 1
        f = findings[0]
        assert f.detector == "d8_spend_concentration"
        assert f.monthly_cost_impact_usd == 0.0  # informational — never a claimed saving
        assert "chat" in f.fix_text and "%" in f.fix_text
        assert f.evidence  # counts-only evidence attached

    def test_single_route_is_never_flagged(self) -> None:
        frame = synth_frame([{"tag": "only", "prompt_tokens": 1_000_000} for _ in range(2)])
        assert D8SpendConcentration().run(frame, ctx_for(frame)) == []

    def test_even_split_below_threshold_not_flagged(self) -> None:
        # three routes each ~33% of spend — none clears the 50% bar
        frame = synth_frame([{"tag": t, "prompt_tokens": 1_000_000} for t in ("a", "b", "c")])
        assert D8SpendConcentration().run(frame, ctx_for(frame)) == []

    def test_untagged_spend_never_anchors(self) -> None:
        # a dominant but UNTAGGED bucket is not an actionable route
        frame = synth_frame(
            [
                {"tag": "", "prompt_tokens": 1_000_000},
                {"tag": "", "prompt_tokens": 1_000_000},
                {"tag": "named", "prompt_tokens": 1000},
            ]
        )
        assert D8SpendConcentration().run(frame, ctx_for(frame)) == []


@pytest.mark.verifies_requirement("FR-33")
class TestD9IneffectiveCache:
    """D9 — cache written but rarely read = net cost. Money math on OBSERVED
    billed tokens; golden derived in pricing_golden_NOTES.md (D9 section).
    Disjoint from D2 by construction (D2 requires cache_write_tokens == 0)."""

    # (6.25-5)*2000/1e6 - (5-0.5)*100/1e6 = 0.00205/row; x5 rows x30/1day = 0.3075
    GOLDEN_MONTHLY = 0.3075

    def _net_loss_frame(self) -> pd.DataFrame:
        return synth_frame(
            [
                {
                    "provider": "anthropic",
                    "model": "claude-opus-4-8",
                    "tag": "cachey",
                    "prompt_tokens": 3000,
                    "cache_write_tokens": 2000,
                    "cached_tokens": 100,
                }
                for _ in range(5)
            ]
        )

    def test_01_golden_net_loss(self) -> None:
        frame = self._net_loss_frame()
        findings = D9IneffectiveCache().run(frame, ctx_for(frame))
        assert len(findings) == 1
        f = findings[0]
        assert f.detector == "d9_ineffective_cache"
        assert f.monthly_cost_impact_usd == pytest.approx(self.GOLDEN_MONTHLY, abs=1e-9)
        assert f.confidence is Confidence.CONSERVATIVE  # observed billed tokens
        assert "cachey" in f.fix_text
        assert f.detail and f.detail.get("route") == "cachey"  # named for the list

    def test_02_net_positive_caching_is_silent(self) -> None:
        # reads dominate writes → caching pays off → not flagged
        frame = synth_frame(
            [
                {
                    "provider": "anthropic",
                    "model": "claude-opus-4-8",
                    "tag": "good",
                    "prompt_tokens": 3000,
                    "cache_write_tokens": 100,
                    "cached_tokens": 2000,
                }
                for _ in range(5)
            ]
        )
        assert D9IneffectiveCache().run(frame, ctx_for(frame)) == []

    def test_03_no_write_premium_model_is_silent(self) -> None:
        # a model whose cache_write defaults to input can never net-lose
        frame = synth_frame(
            [
                {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "tag": "x",
                    "prompt_tokens": 3000,
                    "cache_write_tokens": 2000,
                    "cached_tokens": 0,
                }
                for _ in range(5)
            ]
        )
        assert D9IneffectiveCache().run(frame, ctx_for(frame)) == []

    def test_04_disjoint_from_d2(self) -> None:
        # the D9 case (cache_write>0) is invisible to D2, and vice versa —
        # savings can never double-count on one route.
        frame = self._net_loss_frame()
        assert D2MissingCache().run(frame, ctx_for(frame)) == []


@pytest.mark.verifies_requirement("FR-33")
class TestD10SpendAnomaly:
    """D10 — deterministic temporal spend-anomaly detection (founder 2026-07-25,
    "dynamic analysis based on logs"). Robust (median + MAD) daily-spike detection
    vs the audit's own baseline; informational ($0 claimed). Rate-independent
    goldens: daily spend is proportional to row count on identical rows, so the
    flagged MULTIPLE (day / median) cancels the rate and is hand-derivable."""

    # July, N days each with `n` identical claude-haiku rows; day `spike_day` gets
    # `spike_n` rows (optionally a different model/route) — a clean spend series.
    def _series(
        self,
        baseline_days: int,
        n: int,
        spike_day: int | None = None,
        spike_n: int = 0,
        spike_model: str = "claude-haiku-4-5",
        spike_tag: str = "chat",
        baseline_counts: list[int] | None = None,
    ) -> pd.DataFrame:
        rows: list[dict] = []
        for d in range(1, baseline_days + 1):
            count = baseline_counts[d - 1] if baseline_counts else n
            for _ in range(count):
                rows.append(
                    {
                        "ts": datetime(2026, 7, d, 12, tzinfo=UTC),
                        "model": "claude-haiku-4-5",
                        "tag": "chat",
                        "prompt_tokens": 2000,
                        "completion_tokens": 100,
                    }
                )
        if spike_day is not None:
            for _ in range(spike_n):
                rows.append(
                    {
                        "ts": datetime(2026, 7, spike_day, 12, tzinfo=UTC),
                        "model": spike_model,
                        "tag": spike_tag,
                        "prompt_tokens": 2000,
                        "completion_tokens": 100,
                    }
                )
        return synth_frame(rows)

    def test_01_flags_spike_multiple_is_rate_independent_golden(self) -> None:
        # 7 quiet days (2 rows each) + 1 day of 20 identical rows → the spike day
        # is exactly 10x the median day, whatever the rate is (rows cancel).
        frame = self._series(7, 2, spike_day=8, spike_n=20)
        findings = D10SpendAnomaly().run(frame, ctx_for(frame))
        assert len(findings) == 1
        f = findings[0]
        assert f.detector == "d10_spend_anomaly"
        assert f.id == "D10-001"
        assert f.monthly_cost_impact_usd == 0.0  # informational — never a claimed saving
        assert f.confidence is Confidence.ESTIMATED
        assert f.detail["day"] == "2026-07-08"
        assert f.detail["multiple"] == pytest.approx(10.0)
        assert f.severity is Severity.HIGH  # a 10x day is loud (deviation-scaled)
        assert f.detail["robust_z"] is None  # flat baseline → MAD 0, z undefined
        assert f.evidence and f.evidence[0].note == "spend spike"
        assert "2026-07-08" in f.fix_text and "typical day" in f.fix_text

    def test_02_attributes_the_top_driver_model_and_route(self) -> None:
        # baseline is haiku/chat; the spike day is dominated by opus/batch.
        frame = self._series(
            7, 2, spike_day=8, spike_n=8, spike_model="claude-opus-4-8", spike_tag="batch"
        )
        f = D10SpendAnomaly().run(frame, ctx_for(frame))[0]
        assert f.detail["model"] == "claude-opus-4-8"
        assert f.detail["top_route"] == "batch"
        assert "claude-opus-4-8" in f.fix_text and "batch" in f.fix_text

    def test_03_dormant_below_min_days(self) -> None:
        # 6 days with a spike: below the weekly baseline → silent, never guesses.
        frame = self._series(6, 2, spike_day=6, spike_n=40)
        assert D10SpendAnomaly().run(frame, ctx_for(frame)) == []

    def test_04_silent_on_flat_spend(self) -> None:
        # 10 identical days, no spike → nothing flagged (no false positive).
        frame = self._series(10, 3)
        assert D10SpendAnomaly().run(frame, ctx_for(frame)) == []

    def test_05_robust_baseline_two_masking_spikes_a_mean_detector_would_miss(self) -> None:
        # 8 quiet days + TWO big spike days (days 5 and 8). The two spikes inflate a
        # mean+std scale so much that each spike's OWN mean/std z falls below the bar
        # (they mask each other) — a mean-based detector MISSES them. median + MAD are
        # unmoved, so D10 catches BOTH. This is the robustness the detector is built on.
        frame = self._series(10, 1, baseline_counts=[1, 1, 1, 1, 50, 1, 1, 50, 1, 1])
        findings = D10SpendAnomaly().run(frame, ctx_for(frame))
        assert [f.detail["day"] for f in findings] == ["2026-07-05", "2026-07-08"]
        # ...prove a mean+std detector would have MISSED them: the spike's mean/std
        # z-score is below the same threshold the robust detector clears.
        daily = frame.groupby(frame["ts"].dt.date)["cost_usd"].sum()
        mean, std = float(daily.mean()), float(daily.std(ddof=0))
        z_meanstd = (float(daily.max()) - mean) / std
        assert z_meanstd < make_settings().d10_z_threshold

    def test_06_z_gate_active(self) -> None:
        # varied baseline (MAD>0) + spike fires by default; an unreachable z bar
        # suppresses it — proving the statistical gate is wired.
        frame = self._series(7, 2, spike_day=8, spike_n=12, baseline_counts=[2, 3, 2, 3, 2, 3, 2])
        assert D10SpendAnomaly().run(frame, ctx_for(frame))  # default: flagged
        tuned = make_settings(d10_z_threshold=1000.0)
        assert D10SpendAnomaly().run(frame, ctx_for(frame, tuned)) == []

    def test_07_multiple_gate_active(self) -> None:
        # a day only 1.5x the median never clears the materiality bar (spike_mult=2).
        frame = self._series(7, 2, spike_day=8, spike_n=3)  # day8 = 3 rows vs 2 = 1.5x
        assert D10SpendAnomaly().run(frame, ctx_for(frame)) == []

    def test_08_severity_scales_with_the_deviation_multiple(self) -> None:
        # loudness is the deviation's OWN magnitude (x a typical day): >=10x HIGH,
        # >=4x MED, else LOW — scale-free, NOT the monthly-USD scale the savings
        # detectors use (an anomaly makes no monthly claim to scale).
        hi = self._series(7, 2, spike_day=8, spike_n=20)  # 10x
        md = self._series(7, 2, spike_day=8, spike_n=10)  # 5x
        lo = self._series(7, 2, spike_day=8, spike_n=5)  # 2.5x
        assert D10SpendAnomaly().run(hi, ctx_for(hi))[0].severity is Severity.HIGH
        assert D10SpendAnomaly().run(md, ctx_for(md))[0].severity is Severity.MED
        assert D10SpendAnomaly().run(lo, ctx_for(lo))[0].severity is Severity.LOW

    def test_09_untagged_spike_flags_on_model_alone(self) -> None:
        # a spike with no route tag still flags (driver = model), route is None.
        frame = self._series(7, 2, spike_day=8, spike_n=20, spike_tag="")
        f = D10SpendAnomaly().run(frame, ctx_for(frame))[0]
        assert f.detail["top_route"] is None
        assert "on route" not in f.fix_text

    def test_10_two_spikes_number_chronologically(self) -> None:
        frame = self._series(10, 2, baseline_counts=[2, 20, 2, 2, 2, 2, 20, 2, 2, 2])
        findings = D10SpendAnomaly().run(frame, ctx_for(frame))
        assert [f.id for f in findings] == ["D10-001", "D10-002"]
        assert [f.detail["day"] for f in findings] == ["2026-07-02", "2026-07-07"]

    def test_11_dormant_on_short_real_fixture(self, waste_pack: pd.DataFrame) -> None:
        # the committed waste_pack spans 3 days — d10 must not fabricate a spike
        # on it (keeps run_all's detector set at d1-d6 for that fixture).
        assert D10SpendAnomaly().run(waste_pack, ctx_for(waste_pack)) == []

    def test_12_empty_frame_is_silent(self) -> None:
        frame = self._series(7, 1).iloc[0:0]  # a real priced frame, emptied to 0 rows
        assert D10SpendAnomaly().run(frame, ctx_for(frame)) == []

    def test_13_all_unpriced_rows_are_silent(self) -> None:
        # every row is an unpriced model (NaN cost) → nothing to analyse, no crash.
        frame = synth_frame(
            [
                {"ts": datetime(2026, 7, d, 12, tzinfo=UTC), "model": "made-up-model-xyz"}
                for d in range(1, 9)
            ]
        )
        assert frame["cost_usd"].isna().all()
        assert D10SpendAnomaly().run(frame, ctx_for(frame)) == []

    def test_14_degenerate_median_zero_is_silent(self) -> None:
        # >half the days spent nothing (zero-token calls → $0) → median is 0, no
        # baseline to deviate from → silent (guards the divide), never a crash.
        rows = [
            {"ts": datetime(2026, 7, d, 12, tzinfo=UTC), "prompt_tokens": 0, "completion_tokens": 0}
            for d in range(1, 5)  # 4 zero-cost days
        ] + [
            {
                "ts": datetime(2026, 7, d, 12, tzinfo=UTC),
                "prompt_tokens": 2000,
                "completion_tokens": 100,
            }
            for d in range(5, 8)  # 3 normal days
        ]
        frame = synth_frame(rows)
        assert D10SpendAnomaly().run(frame, ctx_for(frame)) == []


class TestFindingsClarity:
    """Findings clarity (founder 2026-07-25, "work through what is worth fixing"):
    a savings finding that would render as $0.00 is noise and is dropped by the
    materiality floor; an informational pointer ($0.0 exactly) is always kept; and
    every per-route/model savings finding names its route so many findings of the
    same kind read as DISTINCT, not duplicated."""

    def test_floor_drops_small_savings_keeps_informational(self, waste_pack: pd.DataFrame) -> None:
        default = run_all(waste_pack, ctx_for(waste_pack))
        assert any(f.monthly_cost_impact_usd > 0 for f in default)  # savings present
        assert any(f.monthly_cost_impact_usd == 0.0 for f in default)  # informational present
        # a floor above every savings figure leaves ONLY the $0 informational pointers —
        # proving savings are dropped by materiality but informational is never dropped.
        tuned = make_settings(min_finding_monthly_usd=1e9)
        high = run_all(waste_pack, ctx_for(waste_pack, tuned))
        assert high and all(f.monthly_cost_impact_usd == 0.0 for f in high)
        assert {f.id for f in high} <= {f.id for f in default}  # nothing invented

    def test_default_floor_keeps_every_material_finding(self, waste_pack: pd.DataFrame) -> None:
        # the shipped floor ($0.005) is below every real waste_pack finding, so the
        # honest set is unchanged — the floor only ever removes $0.00 noise.
        assert len(run_all(waste_pack, ctx_for(waste_pack))) == 6

    def test_savings_findings_name_their_route(self, waste_pack: pd.DataFrame) -> None:
        by_det = {f.detector: f for f in run_all(waste_pack, ctx_for(waste_pack))}
        # every per-route/model savings detector names its target so the list reads
        # as distinct findings, not repeated identical text.
        for det in (
            "d1_oversized_model",
            "d2_missing_cache",
            "d3_prompt_bloat",
            "d4_retry_storm",
            "d6_chatty_loop",
        ):
            assert det in by_det, det
            assert by_det[det].detail and by_det[det].detail.get("route"), det

    def test_route_label_placeholder_never_renders_nan_or_none(self) -> None:
        from tokenops_cost_auditor.services.rules.findings import route_label

        assert route_label("checkout") == "checkout"
        assert route_label("") == "(untagged)"
        assert route_label(None) == "(untagged)"
        assert route_label(float("nan")) == "(untagged)"
