"""R-FLYWHEEL L3 (deterministic-now) — before-the-invoice forecast + anomaly.

Golden math (exact dollars, hand-derived) locks the money projection; the edge
cases lock the Honesty Law (no projecting from noise) and the no-false-alarm
guarantee for an account whose usage has gone quiet.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import Base, Source, SourceUsage, User
from tokenops_cost_auditor.services.forecast import project_cycle
from tokenops_cost_auditor.services.pricing.table import PricingTable, Rate

# input=output=cache_read=$1/1M => a bucket's cost ($) == (prompt+completion) tokens / 1e6.
TABLE = PricingTable(
    version="t",
    last_verified=None,
    _entries={
        ("openai", "testmodel"): (
            Rate(input=1.0, output=1.0, cache_read=1.0, cache_write=1.0,
                 effective_from=date(2026, 1, 1)),
        )
    },
)
NOW = datetime(2026, 7, 16, tzinfo=UTC)  # today=Jul16 -> yesterday=Jul15, 15 elapsed days, July=31d


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path}/fc.db")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture()
def user_id(session: Session) -> str:
    user = User(email="fc@example.com")
    session.add(user)
    session.flush()
    src = Source(user_id=user.id, provider="openai", label="acct", credentials_encrypted="x")
    session.add(src)
    session.flush()
    session._src_id = src.id  # type: ignore[attr-defined]
    session.commit()
    return user.id


def _add(session: Session, day: date, dollars: float) -> None:
    session.add(
        SourceUsage(
            source_id=session._src_id,  # type: ignore[attr-defined]
            day=day,
            model="testmodel",
            calls=1,
            prompt_tokens=int(dollars * 1_000_000),  # $1 == 1M prompt tokens here
            completion_tokens=0,
            cached_tokens=0,
            provenance={"t": "test"},
        )
    )


class TestForecastGolden:
    def test_projection_and_anomaly_exact(self, session: Session, user_id: str) -> None:
        # baseline window (Apr2..Jun30): $20/mo avg from $60 over the quarter
        _add(session, date(2026, 4, 15), 20.0)
        _add(session, date(2026, 5, 15), 20.0)
        _add(session, date(2026, 6, 15), 20.0)
        # this month (Jul1..Jul15): $15 over 15 elapsed days -> run-rate $31/mo
        _add(session, date(2026, 7, 2), 5.0)
        _add(session, date(2026, 7, 8), 5.0)
        _add(session, date(2026, 7, 14), 5.0)
        session.commit()

        f = project_cycle(session, TABLE, user_id, now=NOW)
        assert f.ready is True
        assert f.days_elapsed == 15 and f.days_in_month == 31
        assert f.mtd_usd == pytest.approx(15.0)
        assert f.projected_usd == pytest.approx(31.0)  # 15/15*31
        assert f.baseline_usd == pytest.approx(20.0)  # 60 / (90/30)
        assert f.over_pct == pytest.approx(55.0)  # (31-20)/20*100
        assert f.anomaly is True  # 55% >= 30% threshold
        assert "projected from 15 of 31 days" in f.basis

    def test_below_threshold_is_not_an_anomaly(self, session: Session, user_id: str) -> None:
        _add(session, date(2026, 4, 15), 20.0)
        _add(session, date(2026, 5, 15), 20.0)
        _add(session, date(2026, 6, 15), 20.0)  # baseline $20/mo
        _add(session, date(2026, 7, 5), 10.0)  # MTD $10 -> projected 10/15*31 = $20.67
        session.commit()
        f = project_cycle(session, TABLE, user_id, now=NOW)
        assert f.ready is True
        assert f.projected_usd == pytest.approx(10.0 / 15 * 31)
        assert f.anomaly is False  # ~3% over baseline, under 30%

    def test_quiet_account_does_not_false_alarm(self, session: Session, user_id: str) -> None:
        # the founder's actual shape: real history, but usage stopped before this month
        _add(session, date(2026, 4, 15), 20.0)
        _add(session, date(2026, 5, 15), 20.0)
        _add(session, date(2026, 6, 15), 20.0)
        # NOTHING in July
        session.commit()
        f = project_cycle(session, TABLE, user_id, now=NOW)
        assert f.ready is True
        assert f.mtd_usd == pytest.approx(0.0)
        assert f.projected_usd == pytest.approx(0.0)
        assert f.anomaly is False  # trending DOWN is never an overspend alert

    def test_unpriced_baseline_holds_the_alert(self, session: Session, user_id: str) -> None:
        # a model priced only from June: April/May baseline usage is unpriced,
        # so the baseline is understated -> we must NOT fire a false overspend.
        table = PricingTable(
            version="t", last_verified=None,
            _entries={("openai", "testmodel"): (
                Rate(input=1.0, output=1.0, cache_read=1.0, cache_write=1.0,
                     effective_from=date(2026, 6, 1)),
            )},
        )
        _add(session, date(2026, 4, 15), 20.0)  # unpriced (before 2026-06-01)
        _add(session, date(2026, 5, 15), 20.0)  # unpriced
        _add(session, date(2026, 6, 15), 20.0)  # priced
        _add(session, date(2026, 7, 2), 5.0)
        _add(session, date(2026, 7, 8), 5.0)
        _add(session, date(2026, 7, 14), 5.0)  # MTD $15 -> projected $31
        session.commit()
        f = project_cycle(session, table, user_id, now=NOW)
        assert f.baseline_partial is True
        assert f.anomaly is False  # projection shown, alert held
        assert "hold the overspend alert" in f.basis

    def test_unpriced_current_month_is_flagged_not_silent(
        self, session: Session, user_id: str
    ) -> None:
        # cold-review f.1: unpriced usage THIS month understates the projection.
        # The number must say so; the alert may still fire (understated crossing
        # the threshold is conservative-safe, so no false positive is possible).
        _add(session, date(2026, 4, 15), 20.0)
        _add(session, date(2026, 5, 15), 20.0)
        _add(session, date(2026, 6, 15), 20.0)  # baseline fully priced, $20/mo
        _add(session, date(2026, 7, 2), 20.0)
        _add(session, date(2026, 7, 8), 20.0)  # $40 priced -> projected $82.67, +313%
        session.add(  # plus usage of a model the table can't price
            SourceUsage(
                source_id=session._src_id,  # type: ignore[attr-defined]
                day=date(2026, 7, 10),
                model="mystery-model",
                calls=1,
                prompt_tokens=1_000_000,
                completion_tokens=0,
                cached_tokens=0,
                provenance={"t": "test"},
            )
        )
        session.commit()
        f = project_cycle(session, TABLE, user_id, now=NOW)
        assert f.mtd_partial is True
        assert f.mtd_usd == pytest.approx(40.0)  # priced portion only
        assert "understated" in f.basis
        assert f.anomaly is True  # still fires — the real figure is even higher

    def test_insufficient_history_is_honest(self, session: Session, user_id: str) -> None:
        # only a few days of history -> below the honesty threshold
        _add(session, date(2026, 7, 13), 5.0)
        _add(session, date(2026, 7, 14), 5.0)
        session.commit()
        f = project_cycle(session, TABLE, user_id, now=NOW)
        assert f.ready is False
        assert f.baseline_usd is None
        assert "more day" in f.reason
        assert f.basis.startswith("building your forecast")

    def test_too_early_in_the_month_says_so(self, session: Session, user_id: str) -> None:
        # long history, but only 2 elapsed days this month (< MIN_ELAPSED_DAYS)
        _add(session, date(2026, 4, 15), 20.0)
        _add(session, date(2026, 5, 15), 20.0)
        _add(session, date(2026, 6, 15), 20.0)
        session.commit()
        f = project_cycle(session, TABLE, user_id, now=datetime(2026, 7, 3, tzinfo=UTC))
        assert f.ready is False
        assert "into the month" in f.reason

    def test_history_without_prior_spend_says_so(self, session: Session, user_id: str) -> None:
        # >30 days of history and enough elapsed days, but the whole baseline
        # window is $0 -> "no prior spend to compare against yet"
        _add(session, date(2026, 3, 1), 5.0)  # anchors history_days >= 30
        _add(session, date(2026, 7, 5), 5.0)
        session.commit()
        # baseline window Apr2..Jun30 has zero spend (Mar 1 falls outside it)
        f = project_cycle(session, TABLE, user_id, now=NOW)
        assert f.ready is False
        assert f.reason == "no prior spend to compare against yet"
