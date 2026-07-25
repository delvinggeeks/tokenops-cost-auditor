"""Cross-audit efficiency drift — deterministic vitals comparison (founder
2026-07-25, depth-engine "drift" half). Hand-derived deltas/directions; no rate
golden owed (it only diffs already-priced tokenomics figures)."""

from __future__ import annotations

import pytest

from tokenops_cost_auditor.services.dashboard import drift


def _tk(spend: float, cpr: float, cp1k: float, cache: float) -> dict:
    return {
        "monthly_spend_usd": spend,
        "cost_per_request": cpr,
        "cost_per_1k_out": cp1k,
        "cache_hit_rate": cache,
    }


def _by_label(d: drift.Drift) -> dict[str, drift.DriftMetric]:
    return {m.label: m for m in d.metrics}


class TestDrift:
    def test_improved_efficiency_reports_better_and_no_regression(self) -> None:
        d = drift.compute(_tk(1200, 0.008, 4.0, 0.55), _tk(1000, 0.010, 5.0, 0.40), "prev")
        assert d.prior_audit_id == "prev"
        assert d.regressions == ()  # nothing got worse
        m = _by_label(d)
        assert m["Cost per request"].direction == "better"
        assert m["Cost per 1K output tokens"].direction == "better"
        assert m["Cache hit rate"].direction == "better"
        # exact hand-derived delta + pct on one metric (rate-independent arithmetic)
        assert m["Cost per 1K output tokens"].delta == pytest.approx(-1.0)
        assert m["Cost per 1K output tokens"].pct_change == pytest.approx(-0.2)

    def test_worsened_efficiency_lists_regressions(self) -> None:
        d = drift.compute(_tk(1000, 0.0102, 6.25, 0.30), _tk(1000, 0.0102, 5.0, 0.40), "prev")
        # both efficiency metrics that crossed the material bar and got worse
        assert d.regressions == ("Cost per 1K output tokens", "Cache hit rate")
        m = _by_label(d)
        assert m["Cost per 1K output tokens"].direction == "worse"
        assert m["Cache hit rate"].direction == "worse"
        assert m["Cost per request"].direction == "flat"  # unchanged → flat

    def test_small_changes_are_flat_not_a_trend(self) -> None:
        # every change is under the 5% material bar → nothing is called a trend
        d = drift.compute(_tk(1000, 0.010, 5.0, 0.40), _tk(1000, 0.0102, 5.1, 0.41), "prev")
        assert d.regressions == ()
        assert {m.direction for m in d.metrics} == {"flat"}

    def test_monthly_spend_is_context_never_a_regression(self) -> None:
        # spend up 20% is shown as context ("up"), never judged a regression —
        # more spend can simply mean more usage.
        d = drift.compute(_tk(1200, 0.010, 5.0, 0.40), _tk(1000, 0.010, 5.0, 0.40), "prev")
        m = _by_label(d)
        assert m["Monthly spend"].direction == "up"
        assert "Monthly spend" not in d.regressions

    def test_spend_down_is_context_down_not_better(self) -> None:
        d = drift.compute(_tk(800, 0.010, 5.0, 0.40), _tk(1000, 0.010, 5.0, 0.40), "prev")
        assert _by_label(d)["Monthly spend"].direction == "down"  # context, not "better"

    def test_prior_zero_is_new_not_a_verdict_and_guards_the_divide(self) -> None:
        # cache 0.0 → 0.30 has no percentage baseline → "new", NOT a "better" verdict;
        # no ZeroDivision, pct guarded to 0.0, and never counted as a regression.
        d = drift.compute(_tk(1000, 0.010, 5.0, 0.30), _tk(1000, 0.010, 5.0, 0.0), "prev")
        m = _by_label(d)["Cache hit rate"]
        assert m.direction == "new" and m.pct_change == 0.0 and m.delta == pytest.approx(0.30)
        assert d.regressions == ()

    def test_prior_zero_money_metric_is_new_never_a_false_regression(self) -> None:
        # a prior audit with $0 priced spend → cost-per-request / cost-per-1k prior==0.
        # The current cost is a NEW measurement, NEVER a dishonest "worse"/regression
        # (cold gate f.1: an undefined baseline must not fire the "slipping" alarm).
        d = drift.compute(_tk(1000, 0.010, 5.0, 0.40), _tk(0.0, 0.0, 0.0, 0.40), "prev")
        m = _by_label(d)
        assert m["Cost per request"].direction == "new"
        assert m["Cost per 1K output tokens"].direction == "new"
        assert m["Monthly spend"].direction == "new"
        assert d.regressions == ()  # nothing off a zero baseline is a regression
