"""T-EXP-F-01..09 — FR-32 report explorer (R-EXPLORER, founder order 2026-07-23).

The laws under test, not just the happy path:
- NFR-07 extended: every filtered total reconciles to the sum of its parts.
- Overlap law: latest audit wins per (day, model) bucket — money is never
  counted twice (derivation row in fixtures/pricing_golden_NOTES.md).
- FR-21/FR-31: purged audits participate as aggregates + metadata, labeled.
- Tier honesty: connected-account slices state reduced detector coverage.
- FR-30: equiv-spend line renders whenever any audit in view carries it.
- Auth scoping: one user can never see another's numbers.
- R-PERSONA jargon law: no detector ids at headline depth.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    Audit,
    CallAggregate,
    FindingFeedback,
    FindingRow,
    User,
)
from tokenops_cost_auditor.services.dashboard import explorer
from tokenops_cost_auditor.services.report.model import EQUIV_SPEND_LINE

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}
DETECTOR_IDS = re.compile(r"\b(d[1-6]_[a-z_]+)\b")
TAGS = re.compile(r"<[^>]+>")


def visible_text(html: str) -> str:
    """Copy the user reads — form option VALUES legitimately carry detector
    ids (they are machine state, like URLs); strip tags first."""
    return TAGS.sub(" ", html)


def squash(html: str) -> str:
    """Template source wraps sentences across indented lines; collapse all
    whitespace so copy assertions test words, not line breaks."""
    return re.sub(r"\s+", " ", html)


def seed_audit(
    app: FastAPI,
    *,
    email: str = EMAIL,
    when: datetime,
    buckets: list[tuple[date, str, int, int, int, int, float | None]],
    findings: list[tuple[str, str, str, str, float]] = (),  # (fid, detector, route, sev, usd)
    paid_via: str | None = None,
    source_id: str | None = None,
    purged: bool = False,
    equiv: bool = False,
) -> str:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email)
            session.add(user)
            session.flush()
        audit = Audit(
            user_id=user.id,
            status="done",
            row_count=sum(b[2] for b in buckets),
            observed_days=len({b[0] for b in buckets}),
            total_spend_usd=sum(b[6] or 0.0 for b in buckets),
            paid_via=paid_via,
            source_id=source_id,
            equiv_spend=equiv,
            created_at=when,
            report_ready_at=when,
            purged_at=when + timedelta(days=8) if purged else None,
        )
        session.add(audit)
        session.flush()
        for day, model, calls, pt, ct, cht, cost in buckets:
            session.add(
                CallAggregate(
                    audit_id=audit.id,
                    day=day,
                    model=model,
                    calls=calls,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    cached_tokens=cht,
                    cost_usd=cost,
                )
            )
        for fid, detector, route, sev, usd in findings:
            session.add(
                FindingRow(
                    audit_id=audit.id,
                    finding_id=fid,
                    detector=detector,
                    route=route,
                    severity=sev,
                    monthly_impact_usd=usd,
                    confidence="estimated",
                    fix_text="do the fix",
                    evidence_sample=[{"row_idx": 1, "tokens": 100}],
                )
            )
        session.commit()
        return audit.id


def compose_for(app: FastAPI, email: str = EMAIL, **params: str) -> explorer.ExplorerView:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one()
        return explorer.compose(session, user.id, explorer.parse_filters(params))


D1 = datetime(2026, 3, 10, 12, tzinfo=UTC)
D2 = datetime(2026, 5, 20, 12, tzinfo=UTC)


class TestAccess:
    def test_01_auth_required(self, app: FastAPI) -> None:
        """T-EXP-F-09."""
        assert TestClient(app).get("/explore").status_code == 401

    def test_02_zero_state_is_honest(self, app: FastAPI) -> None:
        page = TestClient(app).get("/explore", headers=HDR)
        assert page.status_code == 200
        assert "No history to explore yet" in page.text
        assert "$0.00" not in page.text


class TestMath:
    def test_03_reconciliation(self, app: FastAPI) -> None:
        """T-EXP-F-01: total == Σ by_model == Σ by_period, unfiltered AND filtered."""
        seed_audit(
            app,
            when=D1,
            buckets=[
                (date(2026, 3, 1), "gpt-4o-mini", 100, 1000, 200, 0, 1.25),
                (date(2026, 3, 2), "gpt-4o-mini", 50, 500, 100, 0, 0.60),
                (date(2026, 3, 2), "claude-sonnet-5", 10, 900, 300, 100, 2.10),
            ],
        )
        seed_audit(
            app,
            when=D2,
            buckets=[(date(2026, 5, 1), "gpt-4o", 7, 700, 70, 0, 3.33)],
        )
        for params in ({}, {"from": "2026-03-01", "to": "2026-03-31"}, {"model": "gpt-4o-mini"}):
            view = compose_for(app, **params)
            by_model = sum(m.cost_usd for m in view.by_model)
            by_period = sum(p.cost_usd for p in view.by_period)
            assert view.spend_usd == pytest.approx(by_model, rel=0.005)
            assert view.spend_usd == pytest.approx(by_period, rel=0.005)
            assert view.calls == sum(m.calls for m in view.by_model)
            assert view.calls == sum(p.calls for p in view.by_period)

    def test_04_overlap_latest_audit_wins(self, app: FastAPI) -> None:
        """T-EXP-F-06: re-audited (day, model) buckets are counted ONCE, from
        the most recent audit; the page says so in words."""
        day = date(2026, 3, 5)
        seed_audit(app, when=D1, buckets=[(day, "gpt-4o-mini", 100, 1000, 100, 0, 5.00)])
        seed_audit(app, when=D2, buckets=[(day, "gpt-4o-mini", 120, 1200, 120, 0, 6.00)])
        view = compose_for(app)
        assert view.spend_usd == pytest.approx(6.00)
        assert view.calls == 120
        assert view.overlap_buckets == 1
        page = TestClient(app).get("/explore", headers=HDR)
        assert "most recent audit" in squash(page.text)

    def test_05_date_and_model_filters_narrow(self, app: FastAPI) -> None:
        """T-EXP-F-04."""
        seed_audit(
            app,
            when=D1,
            buckets=[
                (date(2026, 3, 1), "gpt-4o-mini", 100, 1000, 100, 0, 1.00),
                (date(2026, 4, 1), "claude-sonnet-5", 200, 2000, 200, 0, 2.00),
            ],
        )
        assert compose_for(app, **{"from": "2026-04-01"}).spend_usd == pytest.approx(2.00)
        assert compose_for(app, to="2026-03-31").spend_usd == pytest.approx(1.00)
        view = compose_for(app, model="gpt-4o-mini")
        assert view.spend_usd == pytest.approx(1.00)
        assert [m.model for m in view.by_model] == ["gpt-4o-mini"]

    def test_06_hand_edited_params_fall_back(self, app: FastAPI) -> None:
        f = explorer.parse_filters(
            {"tier": "everything", "from": "not-a-date", "status": "hax", "group": "week"}
        )
        assert (f.tier, f.date_from, f.status, f.group) == ("all", None, "any", "auto")


class TestHonesty:
    def test_07_purged_audit_still_counts_with_label(self, app: FastAPI) -> None:
        """T-EXP-F-03: FR-21 keeps aggregates — the slice includes them and
        says the raw logs are gone."""
        seed_audit(
            app,
            when=D1,
            purged=True,
            buckets=[(date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 4.44)],
        )
        view = compose_for(app)
        assert view.spend_usd == pytest.approx(4.44)
        assert view.purged_in_view == 1
        assert "raw logs purged" in TestClient(app).get("/explore", headers=HDR).text

    def test_08_connected_tier_coverage_note(self, app: FastAPI) -> None:
        """T-EXP-F-07."""
        seed_audit(
            app,
            when=D1,
            paid_via="subscription",
            buckets=[(date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        page = TestClient(app).get("/explore", headers=HDR)
        assert "connected provider accounts" in squash(page.text)
        assert "could not run" in squash(page.text)
        # tier filter isolates connected audits
        assert compose_for(app, tier="uploads").audits_in_view == 0
        assert compose_for(app, tier="connected").audits_in_view == 1

    def test_09_equiv_spend_line(self, app: FastAPI) -> None:
        """T-EXP-F-05: FR-30 verbatim whenever any audit in view carries it."""
        seed_audit(
            app,
            when=D1,
            equiv=True,
            buckets=[(date(2026, 3, 1), "claude-sonnet-5", 10, 100, 10, 0, 1.00)],
        )
        assert EQUIV_SPEND_LINE in TestClient(app).get("/explore", headers=HDR).text

    def test_10_unpriced_counted_not_priced(self, app: FastAPI) -> None:
        seed_audit(
            app,
            when=D1,
            buckets=[
                (date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00),
                (date(2026, 3, 1), "mystery-model", 40, 400, 40, 0, None),
            ],
        )
        view = compose_for(app)
        assert view.spend_usd == pytest.approx(1.00)
        assert view.calls == 50
        assert view.unpriced_calls == 40
        assert "counted, not priced" in TestClient(app).get("/explore", headers=HDR).text


class TestFindings:
    def test_11_dedup_latest_occurrence_and_status_filter(self, app: FastAPI) -> None:
        """Repeat findings on the R-Q9 (detector, route) key show once with a
        seen-in count; feedback resolves across audits; status filter works."""
        a1 = seed_audit(
            app,
            when=D1,
            buckets=[(date(2026, 3, 1), "claude-sonnet-5", 10, 100, 10, 0, 1.00)],
            findings=[("D2-001", "d2_missing_cache", "claude-sonnet-5", "high", 500.0)],
        )
        seed_audit(
            app,
            when=D2,
            buckets=[(date(2026, 5, 1), "claude-sonnet-5", 10, 100, 10, 0, 1.00)],
            findings=[
                ("D2-001", "d2_missing_cache", "claude-sonnet-5", "high", 450.0),
                ("D1-001", "d1_oversized_model", "gpt-4o", "med", 90.0),
            ],
        )
        with app.state.session_factory() as session:
            session.add(
                FindingFeedback(audit_id=a1, finding_id="D2-001", verdict="applied", actor=EMAIL)
            )
            session.commit()
        view = compose_for(app)
        assert view.findings_total == 2
        cache = next(i for i in view.findings if i["detector"] == "d2_missing_cache")
        assert cache["seen_in"] == 2
        assert cache["monthly_usd"] == pytest.approx(450.0)  # latest occurrence
        assert cache["verdict"] == "applied"  # resolved across audits by route key
        applied = compose_for(app, status="applied")
        assert [i["detector"] for i in applied.findings] == ["d2_missing_cache"]
        unreviewed = compose_for(app, status="unreviewed")
        assert [i["detector"] for i in unreviewed.findings] == ["d1_oversized_model"]
        by_sev = compose_for(app, severity="med")
        assert [i["detector"] for i in by_sev.findings] == ["d1_oversized_model"]

    def test_12_waste_stat_sums_deduped_findings(self, app: FastAPI) -> None:
        seed_audit(
            app,
            when=D1,
            buckets=[(date(2026, 3, 1), "claude-sonnet-5", 10, 100, 10, 0, 1.00)],
            findings=[
                ("D2-001", "d2_missing_cache", "claude-sonnet-5", "high", 100.0),
                ("D1-001", "d1_oversized_model", "gpt-4o", "med", 50.0),
            ],
        )
        assert compose_for(app).waste_monthly_usd == pytest.approx(150.0)


class TestScoping:
    def test_13_no_cross_user_leakage(self, app: FastAPI) -> None:
        """T-EXP-F-02: the other user's model names and spend never render."""
        seed_audit(
            app,
            when=D1,
            buckets=[(date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        seed_audit(
            app,
            email="other@example.com",
            when=D1,
            buckets=[(date(2026, 3, 1), "secret-model-x", 999, 9990, 999, 0, 777.77)],
        )
        page = TestClient(app).get("/explore", headers=HDR)
        assert "secret-model-x" not in page.text
        assert "777.77" not in page.text
        assert compose_for(app).calls == 10


def seed_source(
    app: FastAPI, email: str = EMAIL, provider: str = "openai", label: str = "openai usage"
) -> str:
    from tokenops_cost_auditor.persistence.models import Source

    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email)
            session.add(user)
            session.flush()
        src = Source(user_id=user.id, provider=provider, label=label)
        session.add(src)
        session.commit()
        return src.id


class TestPerSource:
    """R-MULTI-SOURCE: the explorer switches to one connected account's slice."""

    def test_15_source_filter_isolates_accounts(self, app: FastAPI) -> None:
        sid_a = seed_source(app, label="openai usage")
        sid_b = seed_source(app, label="openai usage #2")
        seed_audit(
            app,
            when=D1,
            paid_via="subscription",
            source_id=sid_a,
            buckets=[(date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        seed_audit(
            app,
            when=D2,
            paid_via="subscription",
            source_id=sid_b,
            buckets=[(date(2026, 5, 1), "gpt-4o", 20, 200, 20, 0, 2.00)],
        )
        seed_audit(  # an upload, outside any account slice
            app,
            when=D1,
            buckets=[(date(2026, 3, 2), "claude-sonnet-5", 5, 50, 5, 0, 4.00)],
        )
        view_a = compose_for(app, source=sid_a)
        assert view_a.spend_usd == pytest.approx(1.00)
        assert [m.model for m in view_a.by_model] == ["gpt-4o-mini"]
        view_b = compose_for(app, source=sid_b)
        assert view_b.spend_usd == pytest.approx(2.00)
        assert compose_for(app).spend_usd == pytest.approx(7.00)  # all data, all tiers
        # The select renders both account labels; the filtered page drops the
        # other account's model.
        page = TestClient(app).get("/explore", headers=HDR, params={"source": sid_a})
        assert "openai usage #2" in page.text  # option in the select
        assert "gpt-4o</td>" not in page.text

    def test_16_unattributed_connected_audits_are_stated(self, app: FastAPI) -> None:
        sid = seed_source(app)
        seed_audit(
            app,
            when=D2,
            paid_via="subscription",
            source_id=sid,
            buckets=[(date(2026, 5, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        seed_audit(  # pre-013 connected audit: subscription, no source_id
            app,
            when=D1,
            paid_via="subscription",
            buckets=[(date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        view = compose_for(app, source=sid)
        assert view.unattributed_connected == 1
        page = TestClient(app).get("/explore", headers=HDR, params={"source": sid})
        assert "tell your connected accounts apart" in squash(page.text)

    def test_17_unknown_source_id_matches_nothing_honestly(self, app: FastAPI) -> None:
        seed_audit(
            app,
            when=D1,
            buckets=[(date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        view = compose_for(app, source="not-a-real-id")
        assert view.audits_in_view == 0 and view.spend_usd == 0.0
        page = TestClient(app).get("/explore", headers=HDR, params={"source": "not-a-real-id"})
        assert "Nothing matches this slice" in page.text


class TestCopy:
    def test_14_purpose_line_and_jargon_law(self, app: FastAPI) -> None:
        """T-EXP-F-08: sidebar destination has a purpose line; headline copy
        carries no detector ids (they may appear only in form values/URLs)."""
        seed_audit(
            app,
            when=D1,
            buckets=[(date(2026, 3, 1), "claude-sonnet-5", 10, 100, 10, 0, 1.00)],
            findings=[("D2-001", "d2_missing_cache", "claude-sonnet-5", "high", 500.0)],
        )
        page = TestClient(app).get("/explore", headers=HDR)
        assert "Slice your entire history" in page.text
        assert not DETECTOR_IDS.search(visible_text(page.text))
        assert ">Explore<" in page.text  # nav destination present


class TestColdReviewRegressions:
    """Gate-round fixes (cold-review f.1/f.3, ux f.1) pinned as tests."""

    def test_18_overlap_tie_resolves_deterministically(self, app: FastAPI) -> None:
        """f.1: two audits with the SAME report_ready_at over the same bucket —
        the winner is fixed by (when, id), never by DB return order."""
        day = date(2026, 3, 5)
        a1 = seed_audit(app, when=D1, buckets=[(day, "gpt-4o-mini", 100, 1000, 100, 0, 5.00)])
        a2 = seed_audit(app, when=D1, buckets=[(day, "gpt-4o-mini", 120, 1200, 120, 0, 6.00)])
        winner_spend = 6.00 if a2 > a1 else 5.00
        for _ in range(3):
            assert compose_for(app).spend_usd == pytest.approx(winner_spend)

    def test_19_unattributed_note_respects_date_window(self, app: FastAPI) -> None:
        """f.3: the "N earlier audits excluded" warning describes the SLICE."""
        sid = seed_source(app)
        seed_audit(
            app,
            when=D2,
            paid_via="subscription",
            source_id=sid,
            buckets=[(date(2026, 5, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        seed_audit(  # unattributed, March data only
            app,
            when=D1,
            paid_via="subscription",
            buckets=[(date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00)],
        )
        assert compose_for(app, source=sid).unattributed_connected == 1
        may_only = compose_for(app, source=sid, **{"from": "2026-05-01", "to": "2026-05-31"})
        assert may_only.unattributed_connected == 0


class TestBareAudits:
    """system-tester f.1: audits with findings but no aggregate rows."""

    def test_20_bare_audit_findings_are_never_silently_dropped(self, app: FastAPI) -> None:
        seed_audit(
            app,
            when=D1,
            buckets=[],
            findings=[("D2-001", "d2_missing_cache", "claude-sonnet-5", "high", 90.0)],
        )
        view = compose_for(app)
        assert view.audits_in_view == 1
        assert view.findings_total == 1
        assert view.no_breakdown_in_view == 1
        assert view.spend_usd == 0.0  # no invented money

    def test_21_bare_audit_respects_date_window_and_model_slice(self, app: FastAPI) -> None:
        seed_audit(
            app,
            when=D1,  # 2026-03-10
            buckets=[],
            findings=[("D2-001", "d2_missing_cache", "claude-sonnet-5", "high", 90.0)],
        )
        # outside the window -> honestly excluded
        assert compose_for(app, **{"from": "2026-05-01"}).audits_in_view == 0
        # a model slice can only be answered by aggregate rows -> excluded
        assert compose_for(app, model="gpt-4o-mini").audits_in_view == 0

    def test_22_filter_miss_on_bare_account_says_nothing_matches(self, app: FastAPI) -> None:
        """system-tester sweep 2 f.2: an active filter that matches nothing
        must say so — never 'No history to explore yet' to an account WITH
        history, even when its audits carry no aggregate rows."""
        seed_audit(
            app,
            when=D1,
            buckets=[],
            findings=[("D2-001", "d2_missing_cache", "claude-sonnet-5", "high", 90.0)],
        )
        page = TestClient(app).get("/explore", headers=HDR, params={"model": "gpt-4o-mini"})
        assert "Nothing matches this slice" in page.text
        assert "No history to explore yet" not in page.text


class TestSavedViews:
    """FR-32 C3 (R-PROCEED 2026-07-23): named filter sets. Export is
    deliberately absent — the registered data-export trigger stands."""

    def _seed_data(self, app: FastAPI) -> None:
        seed_audit(
            app,
            when=D1,
            buckets=[
                (date(2026, 3, 1), "gpt-4o-mini", 10, 100, 10, 0, 1.00),
                (date(2026, 5, 1), "claude-sonnet-5", 20, 200, 20, 0, 2.00),
            ],
        )

    def test_30_save_load_and_narrow(self, app: FastAPI) -> None:
        self._seed_data(app)
        client = TestClient(app)
        resp = client.post(
            "/explore/views",
            headers=HDR,
            data={
                "name": "March mini",
                "params": "from=2026-03-01&to=2026-03-31&model=gpt-4o-mini",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        page = client.get("/explore", headers=HDR)
        assert "March mini" in page.text
        via_view = compose_for(
            app, **{"from": "2026-03-01", "to": "2026-03-31", "model": "gpt-4o-mini"}
        )
        assert via_view.spend_usd == pytest.approx(1.00)

    def test_31_params_are_whitelist_sanitized(self, app: FastAPI) -> None:
        """A hostile params field stores ONLY whitelisted filter keys."""
        client = TestClient(app)
        client.post(
            "/explore/views",
            headers=HDR,
            data={"name": "sneaky", "params": "model=gpt-4o-mini&evil=<script>&tier=hax"},
            follow_redirects=False,
        )
        from tokenops_cost_auditor.persistence.models import SavedView

        with app.state.session_factory() as session:
            row = session.execute(select(SavedView)).scalars().one()
            assert row.params == "model=gpt-4o-mini"  # evil + invalid tier dropped

    def test_32_same_name_replaces_and_scoping_holds(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.post(
            "/explore/views",
            headers=HDR,
            data={"name": "mine", "params": "model=a"},
            follow_redirects=False,
        )
        client.post(
            "/explore/views",
            headers=HDR,
            data={"name": "mine", "params": "model=b"},
            follow_redirects=False,
        )
        from tokenops_cost_auditor.persistence.models import SavedView

        with app.state.session_factory() as session:
            rows = session.execute(select(SavedView)).scalars().all()
            assert len(rows) == 1 and rows[0].params == "model=b"
            view_id = rows[0].id
        other = {"X-User-Email": "other@example.com"}
        assert "mine" not in client.get("/explore", headers=other).text
        assert (
            client.post(
                f"/explore/views/{view_id}/delete", headers=other, follow_redirects=False
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/explore/views/{view_id}/delete", headers=HDR, follow_redirects=False
            ).status_code
            == 303
        )

    def test_33_limit_is_stated_plainly(self, app: FastAPI) -> None:
        client = TestClient(app)
        for i in range(20):
            client.post(
                "/explore/views",
                headers=HDR,
                data={"name": f"v{i}", "params": ""},
                follow_redirects=False,
            )
        over = client.post(
            "/explore/views",
            headers=HDR,
            data={"name": "one more", "params": ""},
            follow_redirects=False,
        )
        assert over.status_code == 400
        assert "delete one first" in over.json()["detail"]

    def test_34_serialize_round_trip_covers_every_filter_field(self, app: FastAPI) -> None:
        """vv-gate f.5: a Filters field added without a serialize_filters
        branch must fail HERE — never silently vanish from saved views."""
        import dataclasses
        from urllib.parse import parse_qsl

        full = explorer.Filters(
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            group="month",
            tier="connected",
            source_id="src123",
            model="gpt-4o-mini",
            detector="d2_missing_cache",
            severity="high",
            status="applied",
        )
        rt = explorer.parse_filters(dict(parse_qsl(explorer.serialize_filters(full))))
        assert rt == full  # lossless round-trip with EVERY field non-default
        # The field ledger: adding a Filters field forces updating this test
        # and, with it, the serialize branch the round-trip proves.
        assert {f.name for f in dataclasses.fields(explorer.Filters)} == {
            "date_from",
            "date_to",
            "group",
            "tier",
            "source_id",
            "model",
            "detector",
            "severity",
            "status",
        }
