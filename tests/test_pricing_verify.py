"""R-AUTO-PRICING tests — the strict agent verification gate.

Fixture-driven: a canned feed dict stands in for the live source. Pins:
per-million unit conversion, provider key mapping (azure/ prefix, bedrock
dated/versioned fallbacks), the conditional cache_write comparison, and
the STRICT contract — a mismatch or an uncovered row fails the run; there
is no advisory mode.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from tokenops_cost_auditor.services.pricing.table import PricingTable

# scripts/ is deliberately not a package — load by file path, same pattern
# as test_pricing_sync.py.
_spec = importlib.util.spec_from_file_location(
    "pricing_verify", Path(__file__).parents[1] / "scripts" / "pricing_verify.py"
)
assert _spec is not None and _spec.loader is not None
pv = importlib.util.module_from_spec(_spec)
# register BEFORE exec: the module's frozen dataclass resolves its string
# annotations through sys.modules[cls.__module__] (PEP 563)
sys.modules["pricing_verify"] = pv
_spec.loader.exec_module(pv)
_feed_entry, _per_million, main, verify = pv._feed_entry, pv._per_million, pv.main, pv.verify

TABLE = PricingTable.load()
NOW = datetime(2026, 7, 23, tzinfo=UTC)


def full_feed() -> dict:
    """A feed that corroborates every current row of the real table —
    generated FROM the table's own current epochs (unit-inverted), which
    makes the conversion path itself the thing under test."""
    feed: dict[str, dict[str, float]] = {}
    for provider, model in TABLE.entries():
        try:
            rate = TABLE.rate(provider, model, NOW.date())
        except Exception:
            continue
        key = f"azure/{model}" if provider == "azure-openai" else model
        entry = {
            "input_cost_per_token": rate.input / 1e6,
            "output_cost_per_token": rate.output / 1e6,
            "cache_read_input_token_cost": rate.cache_read / 1e6,
        }
        if rate.cache_write != rate.input:
            entry["cache_creation_input_token_cost"] = rate.cache_write / 1e6
        feed[key] = entry
    return feed


class TestUnitAndMapping:
    def test_01_per_million_conversion(self) -> None:
        assert _per_million(2.5e-06) == 2.5
        assert _per_million(1e-07) == 0.1
        assert _per_million(None) is None

    def test_02_azure_prefix_and_bedrock_dated_fallback(self) -> None:
        feed = {
            "azure/gpt-5.4": {"input_cost_per_token": 2.5e-06},
            "anthropic.claude-haiku-4-5-20251001-v1:0": {"input_cost_per_token": 1e-06},
        }
        assert _feed_entry(feed, "azure-openai", "gpt-5.4") == (
            "azure/gpt-5.4",
            feed["azure/gpt-5.4"],
        )
        key, _ = _feed_entry(feed, "bedrock", "anthropic.claude-haiku-4-5")
        assert key == "anthropic.claude-haiku-4-5-20251001-v1:0"
        assert _feed_entry(feed, "openai", "gpt-nonexistent") is None


class TestStrictContract:
    def test_03_full_pass_over_the_real_table(self) -> None:
        verdicts = verify(TABLE, full_feed(), today=NOW)
        assert verdicts and all(v.status == "verified" for v in verdicts)

    def test_04_mismatch_is_named_and_fails(self, tmp_path: Path) -> None:
        feed = full_feed()
        feed["gpt-5.4"]["input_cost_per_token"] = 9.99e-06  # wrong on purpose
        verdicts = verify(TABLE, feed, today=NOW)
        bad = [v for v in verdicts if v.status == "mismatch"]
        assert len(bad) == 1 and bad[0].model == "gpt-5.4"
        assert "9.99" in bad[0].detail  # the divergent number is SHOWN
        feed_file = tmp_path / "feed.json"
        feed_file.write_text(json.dumps(feed))
        assert main(["--feed", str(feed_file)]) == 1  # strict: nonzero exit

    def test_05_uncovered_row_fails(self, tmp_path: Path) -> None:
        feed = full_feed()
        del feed["azure/gpt-5.5"]
        verdicts = verify(TABLE, feed, today=NOW)
        assert any(
            v.status == "uncovered" and v.provider == "azure-openai" and v.model == "gpt-5.5"
            for v in verdicts
        )
        feed_file = tmp_path / "feed.json"
        feed_file.write_text(json.dumps(feed))
        assert main(["--feed", str(feed_file)]) == 1

    def test_06_green_run_exits_zero(self, tmp_path: Path) -> None:
        feed_file = tmp_path / "feed.json"
        feed_file.write_text(json.dumps(full_feed()))
        assert main(["--feed", str(feed_file)]) == 0

    def test_07_structural_write_default_not_compared(self) -> None:
        """cache_write = input is OUR schema default, not a provider-published
        number — the verifier must not demand the feed corroborate it."""
        feed = full_feed()
        # azure rows default cache_write to input; inject a creation cost that
        # would mismatch IF it were (wrongly) compared
        feed["azure/gpt-5.4"]["cache_creation_input_token_cost"] = 3.125e-06
        verdicts = {(v.provider, v.model): v for v in verify(TABLE, feed, today=NOW)}
        assert verdicts[("azure-openai", "gpt-5.4")].status == "verified"
