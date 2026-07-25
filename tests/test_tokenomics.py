"""Deterministic tokenomics breakdown (founder 2026-07-25, enterprise depth engine).

Pins the exact aggregation math: vitals, per-dimension slices, unit economics,
and data coverage. Token-count ratios are hand-derived and independent of the
coster; dollar figures are checked against the coster's own priced cost_usd so a
regression in either surfaces here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from tokenops_cost_auditor.services.dashboard import tokenomics
from tokenops_cost_auditor.services.pricing.coster import apply
from tokenops_cost_auditor.services.pricing.table import PricingTable

TABLE = PricingTable.load()


def _priced(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "provider": "anthropic",
        "model": "claude-opus-4-8",
        "ts": datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "tag": "chat",
        "prefix_hash": "h" * 64,
        "endpoint": "",
        "request_id": "r",
    }
    frame = pd.DataFrame([{**defaults, **r} for r in rows])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    priced, _ = apply(TABLE, frame)
    return priced


class TestTokenomicsVitals:
    def test_vitals_and_ratios_are_exact(self) -> None:
        frame = _priced([{"cached_tokens": 100}, {"cached_tokens": 100}])  # 2 rows
        tk = tokenomics.compute(frame)
        # token counts + ratios are hand-derived, independent of the coster
        assert tk.tokens_in == 2000
        assert tk.tokens_out == 400
        assert tk.tokens_cached == 200
        assert tk.cache_hit_rate == pytest.approx(0.1)  # 200 / 2000
        assert tk.out_in_ratio == pytest.approx(0.2)  # 400 / 2000
        # dollars reconcile to the coster's own priced cost, x30/observed_days (1 day)
        total = float(frame["cost_usd"].sum())
        assert tk.monthly_spend_usd == pytest.approx(total * 30)
        assert tk.cost_per_request == pytest.approx(total / 2)
        assert tk.cost_per_1k_out == pytest.approx(total / 0.4)  # 400 out / 1000
        assert tk.pct_priced == 1.0
        assert tk.pct_attributed == 1.0


class TestTokenomicsSlices:
    def test_by_model_and_route_ranked_and_shares_sum(self) -> None:
        frame = _priced(
            [
                {"model": "claude-opus-4-8", "tag": "chat", "prompt_tokens": 5000},
                {"model": "gpt-5.6-luna", "provider": "openai", "tag": "b", "prompt_tokens": 500},
            ]
        )
        tk = tokenomics.compute(frame)
        # ranked by monthly $ desc; opus row is the pricier one
        assert [s.name for s in tk.by_model] == ["claude-opus-4-8", "gpt-5.6-luna"]
        assert tk.by_model[0].share > tk.by_model[1].share
        assert sum(s.share for s in tk.by_model) == pytest.approx(1.0)
        assert {s.name for s in tk.by_route} == {"chat", "b"}

    def test_untagged_spend_is_its_own_slice_and_lowers_attribution(self) -> None:
        frame = _priced([{"tag": "chat"}, {"tag": ""}])  # one tagged, one untagged
        tk = tokenomics.compute(frame)
        assert tk.pct_attributed == pytest.approx(0.5)
        assert tokenomics.UNTAGGED in {s.name for s in tk.by_route}


class TestTokenomicsCoverage:
    def test_unpriced_rows_excluded_from_money_but_counted_in_coverage(self) -> None:
        frame = _priced([{}, {"model": "no-such-model-9", "provider": "openai"}])
        tk = tokenomics.compute(frame)
        assert tk.pct_priced == pytest.approx(0.5)  # 1 of 2 rows priced
        # the unpriced row contributes no money and no model slice
        assert [s.name for s in tk.by_model] == ["claude-opus-4-8"]

    def test_empty_frame_is_all_zero_not_a_crash(self) -> None:
        # a real priced frame (with columns) sliced to zero rows
        tk = tokenomics.compute(_priced([{}]).iloc[0:0])
        assert tk.monthly_spend_usd == 0.0
        assert tk.by_model == () and tk.by_route == ()
        assert tk.cache_hit_rate == 0.0 and tk.cost_per_request == 0.0
