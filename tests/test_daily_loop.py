"""R-DAILY-LOOP (founder-ratified 2026-07-22) — the daily surface.

The retention mechanism the penetration pricing depends on: one email per
paying customer per day carrying yesterday's spend per source (same rate
math as audits), month-to-date, and staged 50/80/100% budget progress; the
dashboard "Yesterday" tile shows the same numbers. R-STMT-GATING grammar:
a zero-spend day stamps and stays silent.

The fixture model claude-fable-5 is priced $10/M input in the verified
rate card, so 1M uncached prompt tokens = an exact $10.00 — golden-number
discipline without a spreadsheet.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    AlertEvent,
    AlertRule,
    Audit,
    Source,
    SourceUsage,
    Subscription,
    User,
    utcnow,
)
from tokenops_cost_auditor.services.connectors import daily, schedule
from tokenops_cost_auditor.services.pricing.table import PricingTable as _PT
from tokenops_cost_auditor.services.pricing.table import Rate as _Rate

EMAIL = "daily@example.com"
# Anchored to mid-month, not the real clock: the budget-stage tests advance NOW by up
# to two days and assert on MONTH-TO-DATE spend, so a real-clock NOW straddles the month
# boundary on the last days of a month and the month-to-date total resets under them.
NOW = datetime.now(UTC).replace(day=15, hour=12, minute=0, second=0, microsecond=0)
YESTERDAY = (NOW - timedelta(days=1)).date()


class CapturingMail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def alert(self, to_email: str, subject: str, body: str) -> None:
        self.sent.append((to_email, subject, body))

    def magic_link(self, to_email: str, link_url: str) -> None:
        pass

    def report_ready(self, to_email: str, report_url: str) -> None:
        pass


def _paid_user(app: FastAPI, email: str = EMAIL, currency: str = "USD") -> str:
    provider = "razorpay" if currency == "INR" else "stripe"
    with app.state.session_factory() as session:
        user = User(email=email)
        session.add(user)
        session.flush()
        session.add(
            Subscription(
                user_id=user.id, provider=provider, plan="pro", status="active", currency=currency
            )
        )
        session.commit()
        return user.id


def _source(app: FastAPI, user_id: str, label: str = "Claude Code") -> str:
    with app.state.session_factory() as session:
        source = Source(
            user_id=user_id, provider="anthropic", label=label, credentials_encrypted="x"
        )
        session.add(source)
        session.commit()
        return source.id


def _past_first_run(app: FastAPI, user_id: str) -> None:
    """A completed audit → past the guided first-run state, so the live widget
    grid (which holds the daily-loop 'Yesterday' tile) renders. In production a
    connected source kicks off an audit (R-LIVE-AUDIT), so daily data and a
    completed audit always coexist; these tests make that explicit."""
    with app.state.session_factory() as session:
        session.add(
            Audit(
                user_id=user_id,
                status="done",
                observed_days=7,
                total_spend_usd=100.0,
                report_ready_at=utcnow(),
            )
        )
        session.commit()


def _usage(
    app: FastAPI,
    source_id: str,
    day=YESTERDAY,
    prompt: int = 1_000_000,
    model: str = "claude-fable-5",
) -> None:
    with app.state.session_factory() as session:
        session.add(
            SourceUsage(
                source_id=source_id,
                day=day,
                model=model,
                calls=10,
                prompt_tokens=prompt,
                completion_tokens=0,
                cached_tokens=0,
            )
        )
        session.commit()


def _run(app: FastAPI, mail: CapturingMail) -> dict[str, int]:
    with app.state.session_factory() as session:
        return daily.run_digests(
            session, app.state.settings, app.state.pricing_table, mail, now=NOW
        )


# A fully-priced synthetic card ($10/M input from 2026-01-01) so the digest
# forecast tests exercise the ALERT wiring, not rate-card effective_from edges
# (the real card starts 2026-06-01, which would leave a baseline window unpriced).
_FC_TABLE = _PT(
    version="fc",
    last_verified=None,
    _entries={
        ("anthropic", "claude-fable-5"): (
            _Rate(
                input=10.0,
                output=50.0,
                cache_read=1.0,
                cache_write=12.5,
                effective_from=date(2026, 1, 1),
            ),
        )
    },
)


class TestForecastAnomalyInDigest:
    """R-FLYWHEEL L3: a projected overspend must reach the customer BEFORE the
    invoice, via the daily digest — even on a day yesterday itself was quiet."""

    def test_projected_overspend_lands_in_the_digest(self, app: FastAPI) -> None:
        # unique email: the shared app DB carries other tests' users, so target
        # this recipient specifically instead of mail.sent[0].
        who = "fc-anomaly@example.com"
        fixed = datetime(2026, 7, 16, tzinfo=UTC)  # day 16 -> 15 elapsed days, ready
        src = _source(app, _paid_user(app, email=who))
        # baseline ~$20/mo across the prior quarter (claude-fable-5 = $10/M input)
        for d in (date(2026, 4, 15), date(2026, 5, 15), date(2026, 6, 15)):
            _usage(app, src, day=d, prompt=2_000_000)  # $20 each
        # this month trending high: $15 over 15 days -> projected $31 (+55%)
        _usage(app, src, day=date(2026, 7, 5), prompt=1_500_000)  # $15
        mail = CapturingMail()
        with app.state.session_factory() as session:
            daily.run_digests(session, app.state.settings, _FC_TABLE, mail, now=fixed)
        mine = [m for m in mail.sent if m[0] == who]
        assert mine, "an anomaly must send even though yesterday (Jul 15) was quiet"
        _to, subject, body = mine[0]
        assert "Heads up" in subject
        assert "On track for" in body

    def test_on_track_account_gets_no_heads_up(self, app: FastAPI) -> None:
        who = "fc-ontrack@example.com"
        fixed = datetime(2026, 7, 16, tzinfo=UTC)
        src = _source(app, _paid_user(app, email=who))
        for d in (date(2026, 4, 15), date(2026, 5, 15), date(2026, 6, 15)):
            _usage(app, src, day=d, prompt=2_000_000)  # baseline $20/mo
        _usage(app, src, day=date(2026, 7, 15), prompt=1_000_000)  # $10 yesterday, in-line
        mail = CapturingMail()
        with app.state.session_factory() as session:
            daily.run_digests(session, app.state.settings, _FC_TABLE, mail, now=fixed)
        mine = [m for m in mail.sent if m[0] == who]
        assert mine  # still sends (yesterday had spend)
        _to, subject, body = mine[0]
        assert "Heads up" not in subject
        assert "On track for" not in body


class TestTheDigest:
    def test_carries_yesterdays_number_per_source(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _usage(app, _source(app, uid))
        mail = CapturingMail()
        stats = _run(app, mail)
        assert stats["digests_sent"] == 1
        to, subject, body = mail.sent[0]
        assert to == EMAIL
        assert subject.startswith("$10.00 yesterday")  # the subject carries the number
        assert "Claude Code: $10.00" in body
        assert "Month so far:" in body

    def test_goes_out_at_most_once_per_day(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _usage(app, _source(app, uid))
        mail = CapturingMail()
        assert _run(app, mail)["digests_sent"] == 1
        assert _run(app, mail)["digests_sent"] == 0, "same day, same customer — one email"

    def test_a_zero_spend_day_stamps_and_stays_silent(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _source(app, uid)  # connected, but nothing happened yesterday
        mail = CapturingMail()
        stats = _run(app, mail)
        assert stats["digests_sent"] == 0 and stats["digests_skipped"] == 1
        assert mail.sent == []
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            assert user.last_daily_digest_at is not None, "silence still stamps — no retry storm"

    def test_a_mail_failure_retries_next_tick_instead_of_dropping_the_day(
        self, app: FastAPI
    ) -> None:
        """Readiness audit: the digest stamped-then-sent, so a transient mail
        failure permanently dropped that day. Now it sends first and only
        stamps on success — a failed send leaves the day un-stamped so the
        next tick retries."""
        uid = _paid_user(app)
        _usage(app, _source(app, uid))

        class FlakyMail(CapturingMail):
            def __init__(self) -> None:
                super().__init__()
                self.calls = 0

            def alert(self, to, subject, body):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("smtp hiccup")
                super().alert(to, subject, body)

        mail = FlakyMail()
        stats = _run(app, mail)  # first tick: send raises
        assert stats["digests_sent"] == 0 and stats["digest_errors"] == 1
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            assert user.last_daily_digest_at is None, "a failed send must NOT stamp the day"
        stats2 = _run(app, mail)  # next tick: send succeeds
        assert stats2["digests_sent"] == 1 and len(mail.sent) == 1

    def test_free_plans_get_no_digest(self, app: FastAPI) -> None:
        with app.state.session_factory() as session:
            user = User(email="free@example.com")
            session.add(user)
            session.commit()
            uid = user.id
        _usage(app, _source(app, uid))
        mail = CapturingMail()
        stats = _run(app, mail)
        assert stats["digests_sent"] == 0 and mail.sent == []

    def test_inr_billed_customer_sees_the_rupee_equivalent(self, app: FastAPI) -> None:
        uid = _paid_user(app, currency="INR")
        _usage(app, _source(app, uid))
        mail = CapturingMail()
        _run(app, mail)
        assert "≈₹" in mail.sent[0][2], "INR-billed digests carry the display conversion"


class TestCachedTokenGolden:
    def test_cache_reads_bill_at_the_cache_rate_not_input(self, app: FastAPI) -> None:
        """vv-gate f.2: claude-fable-5 is $10/M input, $1/M cache read, $50/M
        output. 1M prompt of which 500K cached, plus 100K completion:
        (500K*$10 + 500K*$1 + 100K*$50)/1M = $10.50 exactly. A formula
        drift that bills cache reads at input rate would print $15.00."""
        uid = _paid_user(app)
        source = _source(app, uid)
        with app.state.session_factory() as session:
            session.add(
                SourceUsage(
                    source_id=source,
                    day=YESTERDAY,
                    model="claude-fable-5",
                    calls=10,
                    prompt_tokens=1_000_000,
                    completion_tokens=100_000,
                    cached_tokens=500_000,
                )
            )
            session.commit()
        mail = CapturingMail()
        _run(app, mail)
        assert mail.sent[0][1].startswith("$10.50 yesterday")


class TestBudgetStages:
    def _with_budget(self, app: FastAPI, threshold: float) -> str:
        uid = _paid_user(app)
        with app.state.session_factory() as session:
            session.add(
                AlertRule(user_id=uid, rule="soft_budget", threshold=threshold, enabled=True)
            )
            session.commit()
        return uid

    def test_a_stage_fires_once_and_escalates(self, app: FastAPI) -> None:
        uid = self._with_budget(app, threshold=12.0)  # $10 mtd = 83% -> stage 80
        source = _source(app, uid)
        _usage(app, source)
        mail = CapturingMail()
        stats = _run(app, mail)
        assert stats["budget_stages"] == 1
        assert "80% of budget used" in mail.sent[0][1]
        with app.state.session_factory() as session:
            events = session.execute(select(AlertEvent)).scalars().all()
            assert [e.detail["stage"] for e in events] == [80]
        # next day, no new spend: nothing re-fires, nothing re-sends
        with app.state.session_factory() as session:
            later = daily.run_digests(
                session,
                app.state.settings,
                app.state.pricing_table,
                mail,
                now=NOW + timedelta(days=1),
            )
        assert later["budget_stages"] == 0 and later["digests_sent"] == 0
        # crossing 100% escalates exactly one stage further
        _usage(app, source, day=(NOW + timedelta(days=1)).date(), prompt=300_000)  # +$3
        with app.state.session_factory() as session:
            final = daily.run_digests(
                session,
                app.state.settings,
                app.state.pricing_table,
                mail,
                now=NOW + timedelta(days=2),
            )
        assert final["budget_stages"] == 1
        assert mail.sent[-1][1].startswith("Over budget:")


class TestTheTileAndTheTick:
    def test_dashboard_tile_shows_the_same_number(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _usage(app, _source(app, uid))
        _past_first_run(app, uid)  # the tile lives in the post-first-run grid
        page = TestClient(app).get("/dashboard", headers={"X-User-Email": EMAIL}).text
        assert "Yesterday" in page and "$10.00" in page

    def test_tile_names_unpriced_models_instead_of_silently_dropping_them(
        self, app: FastAPI
    ) -> None:
        """Readiness audit: the tile priced only rate-carded models and
        dropped the rest while claiming 'priced on the verified rate card' —
        understating the total silently. Unpriced models must be named."""
        from tokenops_cost_auditor.services.dashboard import metrics

        uid = _paid_user(app)
        source = _source(app, uid)
        _usage(app, source)  # claude-fable-5, priced
        _usage(app, source, model="mystery-model-9")  # no rate card
        with app.state.session_factory() as session:
            w = metrics.yesterday_spend(session, app.state.pricing_table, uid, now=NOW)
        assert "mystery-model-9" in w.provenance
        assert "excludes unpriced" in w.provenance
        assert w.data["unpriced"] == ["mystery-model-9"]

    def test_tile_empty_state_points_at_sources(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _past_first_run(app, uid)  # past first run: the empty tile shows in the grid
        page = TestClient(app).get("/dashboard", headers={"X-User-Email": EMAIL}).text
        assert "The daily loop starts with a connected source" in page

    def test_widget_partial_route_serves_the_tile(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _usage(app, _source(app, uid))
        resp = TestClient(app).get("/dashboard/w/yesterday", headers={"X-User-Email": EMAIL})
        assert resp.status_code == 200 and "$10.00" in resp.text

    def test_the_scheduler_tick_runs_digests(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _usage(app, _source(app, uid))
        mail = CapturingMail()
        with app.state.session_factory() as session:
            stats = schedule.tick(
                session, app.state.settings, app.state.pricing_table, now=NOW, mail=mail
            )
        assert stats["digests_sent"] == 1
        assert any(s.startswith("$10.00 yesterday") for _, s, _ in mail.sent)


class TestTickStageIsolation:
    """Every tick stage is isolated: one stage blowing up must not lose the
    others (the V-D5 law, extended to the digest stage)."""

    def test_a_digest_stage_failure_does_not_block_dunning_or_alerts(
        self, app: FastAPI, monkeypatch
    ) -> None:
        from tokenops_cost_auditor.services.connectors import daily as daily_mod

        def boom(*a, **k):
            raise RuntimeError("digest down")

        monkeypatch.setattr(daily_mod, "run_digests", boom)
        mail = CapturingMail()
        with app.state.session_factory() as session:
            stats = schedule.tick(
                session, app.state.settings, app.state.pricing_table, now=NOW, mail=mail
            )
        assert stats["digest_errors"] == 1
        assert "dunning_moved" in stats and "alerts_fired" in stats, "later stages still ran"

    def test_dunning_and_alert_stage_failures_are_isolated_too(
        self, app: FastAPI, monkeypatch
    ) -> None:
        from tokenops_cost_auditor.services.alerts import dispatch as alerts_mod
        from tokenops_cost_auditor.services.payments import subscriptions as subs_mod

        def boom(*a, **k):
            raise RuntimeError("stage down")

        monkeypatch.setattr(subs_mod, "advance_dunning", boom)
        monkeypatch.setattr(alerts_mod, "run_all", boom)
        mail = CapturingMail()
        with app.state.session_factory() as session:
            stats = schedule.tick(
                session, app.state.settings, app.state.pricing_table, now=NOW, mail=mail
            )
        assert stats["dunning_errors"] == 1
        assert stats["alert_errors"] == 1

    def test_an_audit_failure_counts_and_does_not_stop_the_tick(
        self, app: FastAPI, monkeypatch
    ) -> None:
        uid = _paid_user(app)
        source_id = _source(app, uid)
        with app.state.session_factory() as session:
            source = session.get(Source, source_id)
            source.last_pull_at = NOW  # pull fresh; audit due (never audited)
            session.commit()

        def boom(*a, **k):
            raise RuntimeError("audit down")

        monkeypatch.setattr(schedule, "run_source_audit", boom)
        mail = CapturingMail()
        with app.state.session_factory() as session:
            stats = schedule.tick(
                session, app.state.settings, app.state.pricing_table, now=NOW, mail=mail
            )
        assert stats["audit_errors"] == 1
        assert "digests_sent" in stats, "the tick carried on past the failed audit"


class TestDigestOptOut:
    def test_opting_out_stops_the_daily_digest(self, app: FastAPI) -> None:
        """Wave B digest control: a paid user who turned the daily digest off
        gets none, even with spend to report."""
        uid = _paid_user(app)
        _usage(app, _source(app, uid))
        with app.state.session_factory() as s:
            user = s.execute(select(User).where(User.email == EMAIL)).scalar_one()
            user.daily_digest_emails = False
            s.commit()
        mail = CapturingMail()
        stats = _run(app, mail)
        assert stats["digests_sent"] == 0 and mail.sent == []

    def test_default_and_opt_in_still_send(self, app: FastAPI) -> None:
        uid = _paid_user(app)
        _usage(app, _source(app, uid))
        # default (None) sends
        mail = CapturingMail()
        assert _run(app, mail)["digests_sent"] == 1
