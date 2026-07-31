"""R-LIVE-PRICING — the autonomous pricing sync. Fixture-driven, zero network:
the feed is a dict, never fetched, so these tests never leave the toolchain.

Covers the validation GATES that replace the human approver, refresh vs cover
modes, and the end-to-end proof that a previously-unpriced model (the gpt-4o-mini
incident) becomes priced through the overlay.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

from tokenops_cost_auditor.services.pricing.table import PricingGapError, PricingTable, Rate

# scripts/ is deliberately not a package (ops tooling, not engine code) —
# load by file path like test_ops_scripts.py does. A bare `from scripts
# import ...` only resolves when the repo root happens to sit on sys.path,
# which `uv run pytest` (Makefile/CI invocation) does not guarantee.
_spec = importlib.util.spec_from_file_location(
    "pricing_sync", Path(__file__).parents[1] / "scripts" / "pricing_sync.py"
)
assert _spec is not None and _spec.loader is not None
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

RUN = date(2026, 7, 22)

# A minimal LiteLLM-shaped feed. Costs are per-TOKEN (the feed's unit).
FEED = {
    "sample_spec": {"litellm_provider": "openai"},  # skipped by id
    "gpt-4o-mini": {
        "input_cost_per_token": 1.5e-7,
        "output_cost_per_token": 6e-7,
        "cache_read_input_token_cost": 7.5e-8,
        "litellm_provider": "openai",
        "mode": "chat",
    },
    "gpt-5.4": {  # already in our table -> refresh candidate
        "input_cost_per_token": 1.1e-6,
        "output_cost_per_token": 4.4e-6,
        "litellm_provider": "openai",
    },
    "anthropic/claude-3-5-sonnet-20241022": {  # provider-prefixed key
        "input_cost_per_token": 3e-6,
        "output_cost_per_token": 1.5e-5,
        "cache_read_input_token_cost": 3e-7,
        "cache_creation_input_token_cost": 3.75e-6,
        "litellm_provider": "anthropic",
    },
    "gemini-1.5-pro": {  # dropped: provider we don't price
        "input_cost_per_token": 1e-6,
        "output_cost_per_token": 5e-6,
        "litellm_provider": "vertex_ai",
    },
    "free-model": {  # dropped: never write a $0 rate
        "input_cost_per_token": 0,
        "output_cost_per_token": 0,
        "litellm_provider": "openai",
    },
}


def _table(**entries: tuple[Rate, ...]) -> PricingTable:
    ents = {tuple(k.split("__")): v for k, v in entries.items()}
    return PricingTable(version="t", last_verified=None, _entries=ents)


def _rate(inp: float, out: float, eff: date = date(2026, 6, 1)) -> Rate:
    return Rate(input=inp, output=out, cache_read=inp / 2, cache_write=inp, effective_from=eff)


class TestNormalize:
    def test_per_token_to_per_million_and_provider_filter(self) -> None:
        norm = ps.normalize(FEED)
        # gemini (vertex), free-model ($0), sample_spec all excluded.
        assert set(norm) == {
            ("openai", "gpt-4o-mini"),
            ("openai", "gpt-5.4"),
            ("anthropic", "claude-3-5-sonnet-20241022"),
        }
        mini = norm[("openai", "gpt-4o-mini")]
        assert mini["input"] == 0.15 and mini["output"] == 0.60
        assert mini["cache_read"] == 0.075  # from the feed, ≤ input
        assert mini["cache_write"] == 0.15  # no cache-creation cost -> falls back to input

    def test_prefixed_key_stripped_to_bare_id(self) -> None:
        norm = ps.normalize(FEED)
        assert ("anthropic", "claude-3-5-sonnet-20241022") in norm

    def test_feed_zero_cache_falls_back_to_input_never_zero(self) -> None:
        # cold-review f.3: a $0 cache cost from the feed must not be written as $0
        feed = {
            "m": {
                "input_cost_per_token": 2e-6,
                "output_cost_per_token": 8e-6,
                "cache_read_input_token_cost": 0,  # feed says free -> treat as absent
                "cache_creation_input_token_cost": 0,
                "litellm_provider": "openai",
            }
        }
        cand = ps.normalize(feed)[("openai", "m")]
        assert cand["cache_read"] == cand["input"] == 2.0  # fell back, not 0
        assert cand["cache_write"] == 2.0


class TestGates:
    def test_band_rejects_absurd_rate(self) -> None:
        assert ps.gate_band({"input": 5000, "output": 1, "cache_read": 1, "cache_write": 1})
        assert ps.gate_band({"input": -1, "output": 1, "cache_read": 1, "cache_write": 1})
        assert ps.gate_band({"input": 1, "output": 0, "cache_read": 1, "cache_write": 1})

    def test_band_accepts_plausible(self) -> None:
        cand = {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75}
        assert ps.gate_band(cand) is None


class TestPlanRefresh:
    def test_change_within_band_is_written(self) -> None:
        table = _table(**{"openai__gpt-5.4": (_rate(1.0, 4.0),)})
        out = ps.plan(table, ps.normalize(FEED), RUN, cover=None)
        w = {(x["provider"], x["model"]): x for x in out["writes"]}
        row = w[("openai", "gpt-5.4")]
        assert row["input"] == 1.1
        assert row["effective_from"] == RUN.isoformat()  # a change forward-dates from today

    def test_refresh_never_bulk_imports_unknown_models(self) -> None:
        table = _table(**{"openai__gpt-5.4": (_rate(1.0, 4.0),)})
        out = ps.plan(table, ps.normalize(FEED), RUN, cover=None)
        models = {x["model"] for x in out["writes"]}
        assert "gpt-4o-mini" not in models  # unknown + not covered -> ignored in refresh

    def test_large_jump_is_held_not_applied(self) -> None:
        table = _table(**{"openai__gpt-5.4": (_rate(0.1, 4.0),)})  # feed 1.1 == 11x
        out = ps.plan(table, ps.normalize(FEED), RUN, cover=None)
        assert not any(x["model"] == "gpt-5.4" for x in out["writes"])
        assert any(h["model"] == "gpt-5.4" and "jump" in h["why"] for h in out["held"])

    def test_hold_streak_counts_and_reports_progress(self) -> None:
        """A held swing records how close it is to auto-applying, so the state is
        legible without anyone having to ask a human what to do about it."""
        table = _table(**{"openai__gpt-5.4": (_rate(0.1, 4.0),)})
        out = ps.plan(table, ps.normalize(FEED), RUN, cover=None, prior_streaks={})
        held = next(h for h in out["held"] if h["model"] == "gpt-5.4")
        assert f"corroboration 1/{ps.HOLD_CORROBORATIONS}" in held["why"]
        assert out["held_streaks"]["openai/gpt-5.4"]["n"] == 1

    def test_hold_auto_applies_once_corroborated_no_human_gate(self) -> None:
        """R-AUTO-PRICING forbids a human price gate, so gate 4's hold must expire on
        EVIDENCE. A feed repeating the same rate for HOLD_CORROBORATIONS consecutive
        runs has falsified the one-off-glitch hypothesis, and the swing applies itself."""
        table = _table(**{"openai__gpt-5.4": (_rate(0.1, 4.0),)})
        prior = {"openai/gpt-5.4": {"input": 1.1, "output": 4.4, "n": ps.HOLD_CORROBORATIONS - 1}}
        out = ps.plan(table, ps.normalize(FEED), RUN, cover=None, prior_streaks=prior)
        assert any(x["model"] == "gpt-5.4" for x in out["writes"])  # applied, not held
        assert not any(h["model"] == "gpt-5.4" for h in out["held"])
        assert "openai/gpt-5.4" not in out["held_streaks"]  # streak cleared on apply

    def test_a_flapping_feed_never_accumulates_a_streak(self) -> None:
        """The corroboration must require the SAME candidate each run. A feed that
        reports a different wild number every run is exactly the glitch gate 4 exists to
        stop, so its streak resets rather than creeping up to an automatic apply."""
        table = _table(**{"openai__gpt-5.4": (_rate(0.1, 4.0),)})
        prior = {"openai/gpt-5.4": {"input": 9.9, "output": 9.9, "n": ps.HOLD_CORROBORATIONS - 1}}
        out = ps.plan(table, ps.normalize(FEED), RUN, cover=None, prior_streaks=prior)
        assert not any(x["model"] == "gpt-5.4" for x in out["writes"])  # still held
        assert out["held_streaks"]["openai/gpt-5.4"]["n"] == 1  # reset, not incremented

    def test_noop_is_skipped(self) -> None:
        table = _table(**{"openai__gpt-5.4": (_rate(1.1, 4.4),)})
        out = ps.plan(table, ps.normalize(FEED), RUN, cover=None)
        assert not any(x["model"] == "gpt-5.4" for x in out["writes"])
        assert out["skipped"] >= 1


class TestPlanCover:
    def test_cover_adds_unpriced_model_backdated(self) -> None:
        table = _table(**{"openai__gpt-5.4": (_rate(1.0, 4.0),)})
        # usage id carries a dated snapshot; base-id strip must still match the feed
        out = ps.plan(table, ps.normalize(FEED), RUN, cover={"gpt-4o-mini-2024-07-18"})
        w = {(x["provider"], x["model"]): x for x in out["writes"]}
        assert ("openai", "gpt-4o-mini") in w
        row = w[("openai", "gpt-4o-mini")]
        assert row["input"] == 0.15
        assert row["effective_from"] < RUN.isoformat()  # back-dated to cover the window


class TestPlanDeepen:
    def test_cover_deepens_a_model_priced_today_but_not_historically(self) -> None:
        # gpt-5.4 priceable at RUN (eff 2026-06-01) but January usage can't price;
        # cover must write a back-dated row, not no-op-skip it (the 46,868-call
        # $0.17 incident: covered-today models left their history unpriced).
        table = _table(**{"openai__gpt-5.4": (_rate(1.1, 4.4, eff=date(2026, 6, 1)),)})
        out = ps.plan(table, ps.normalize(FEED), RUN, cover={"gpt-5.4"})
        w = {x["model"]: x for x in out["writes"]}
        assert "gpt-5.4" in w
        expected_eff = RUN - timedelta(days=ps.COVERAGE_BACKDATE_DAYS)
        assert w["gpt-5.4"]["effective_from"] == expected_eff.isoformat()

    def test_cover_of_fully_covered_model_still_noops(self) -> None:
        # already covered across the window -> nothing to write
        table = _table(**{"openai__gpt-5.4": (_rate(1.1, 4.4, eff=date(2025, 1, 1)),)})
        out = ps.plan(table, ps.normalize(FEED), RUN, cover={"gpt-5.4"})
        assert not any(x["model"] == "gpt-5.4" for x in out["writes"])
        assert out["skipped"] >= 1


class TestEndToEndOverlay:
    def test_covered_model_prices_after_overlay_merge(self, tmp_path) -> None:
        base = tmp_path / "prices.yaml"
        base.write_text(
            yaml.safe_dump(
                {
                    "version": "2026-07-17",
                    "last_verified": date(2026, 7, 17),
                    "providers": {
                        "openai": {
                            "models": {
                                "gpt-5.4": [
                                    {
                                        "effective_from": date(2026, 6, 1),
                                        "input": 1.0,
                                        "output": 4.0,
                                    }
                                ]
                            }
                        }
                    },
                }
            )
        )
        overlay = tmp_path / "prices.auto.yaml"

        table = PricingTable.load(path=base, overlay=overlay)  # overlay absent yet
        # gpt-4o-mini unpriced before sync (the incident)
        try:
            table.rate("openai", "gpt-4o-mini-2024-07-18", date(2026, 7, 1))
            raise AssertionError("should have been unpriced")
        except PricingGapError:
            pass

        out = ps.plan(table, ps.normalize(FEED), RUN, cover={"gpt-4o-mini-2024-07-18"})
        ps.write_overlay(ps.merge_overlay(None, out["writes"], RUN), path=overlay)

        merged = PricingTable.load(path=base, overlay=overlay)
        # usage from 3 weeks ago now prices via the back-dated overlay row
        r = merged.rate("openai", "gpt-4o-mini-2024-07-18", date(2026, 7, 1))
        assert r.input == 0.15 and r.output == 0.60
        # the overlay's fresher last_verified wins (never-stale invariant)
        assert merged.last_verified == RUN

    def test_overlay_path_honors_env_for_persistence(self, tmp_path) -> None:
        # founder incident 2026-07-22: the overlay must live on a persistent
        # path (env-configured) so a container recreate never wipes auto-pricing.
        # Checked in a fresh interpreter so the module-load resolution is real.
        custom = tmp_path / "persistent" / "prices.auto.yaml"
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "from tokenops_cost_auditor.services.pricing.table import AUTO_DATA;"
                " print(AUTO_DATA)",
            ],
            env={**os.environ, "PRICING_OVERLAY_PATH": str(custom)},
            capture_output=True,
            text=True,
            check=True,
        )
        assert str(custom) in proc.stdout

    def test_overlay_never_overrides_same_date_base(self, tmp_path) -> None:
        # cold-review f.1: an auto overlay row must NOT supersede a human base
        # rate on the SAME effective_from; it may only add strictly-later dates.
        base = tmp_path / "prices.yaml"
        base.write_text(
            yaml.safe_dump(
                {
                    "version": "v",
                    "last_verified": date(2026, 7, 17),
                    "providers": {
                        "openai": {
                            "models": {
                                "gpt-5.4": [
                                    {
                                        "effective_from": date(2026, 6, 1),
                                        "input": 1.0,
                                        "output": 4.0,
                                    }
                                ]
                            }
                        }
                    },
                }
            )
        )
        overlay = tmp_path / "prices.auto.yaml"
        overlay.write_text(
            yaml.safe_dump(
                {
                    "version": "auto",
                    "last_verified": date(2026, 7, 22),
                    "providers": {
                        "openai": {
                            "models": {
                                "gpt-5.4": [
                                    # SAME date as base — must be ignored (base wins the tie)
                                    {
                                        "effective_from": date(2026, 6, 1),
                                        "input": 9.99,
                                        "output": 9.99,
                                    },
                                    # strictly later — legitimately supersedes (freshness intent)
                                    {
                                        "effective_from": date(2026, 7, 22),
                                        "input": 1.2,
                                        "output": 4.8,
                                    },
                                ]
                            }
                        }
                    },
                }
            )
        )
        t = PricingTable.load(path=base, overlay=overlay)
        assert t.rate("openai", "gpt-5.4", date(2026, 6, 1)).input == 1.0  # base wins tie
        assert t.rate("openai", "gpt-5.4", date(2026, 7, 22)).input == 1.2  # later supersedes

    def test_run_writes_status_and_is_idempotent(self, tmp_path, monkeypatch) -> None:
        base = tmp_path / "prices.yaml"
        base.write_text(
            yaml.safe_dump(
                {
                    "version": "v",
                    "last_verified": date(2026, 7, 17),
                    "providers": {
                        "openai": {
                            "models": {
                                "gpt-5.4": [
                                    {
                                        "effective_from": date(2026, 6, 1),
                                        "input": 1.0,
                                        "output": 4.0,
                                    }
                                ]
                            }
                        }
                    },
                }
            )
        )
        overlay = tmp_path / "prices.auto.yaml"
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        # run() reads these module globals at call time (not load()'s bound defaults)
        monkeypatch.setattr(ps, "AUTO_DATA", overlay)
        monkeypatch.setattr(ps, "DEFAULT_DATA", base)
        monkeypatch.setattr(ps, "fetch_litellm", lambda url=ps.LITELLM_URL: FEED)

        p1 = ps.run(RUN, cover={"gpt-4o-mini"}, dry_run=False, url="x", report_dir=report_dir)
        assert p1["ok"] and p1["written"] >= 1
        status = yaml.safe_load((report_dir / ".ops" / "pricing_sync.json").read_text())
        assert status["mode"] == "cover" and status["written"] >= 1
        rows1 = yaml.safe_load(overlay.read_text())["providers"]["openai"]["models"]["gpt-4o-mini"]

        # second identical run must not stack a duplicate same-date row
        ps.run(RUN, cover={"gpt-4o-mini"}, dry_run=False, url="x", report_dir=report_dir)
        rows2 = yaml.safe_load(overlay.read_text())["providers"]["openai"]["models"]["gpt-4o-mini"]
        assert len(rows2) == len(rows1)
