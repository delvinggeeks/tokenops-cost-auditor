"""Wave A — activation getting-started checklist. Each step self-completes
from real data; the checklist vanishes when done and can be hidden."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.persistence.models import (
    Audit,
    FindingFeedback,
    FindingRow,
    Source,
    User,
    utcnow,
)
from tokenops_cost_auditor.services.dashboard import metrics

EMAIL = "onboard@example.com"
HDR = {"X-User-Email": EMAIL}


def _user(app: FastAPI) -> str:
    with app.state.session_factory() as s:
        u = User(email=EMAIL)
        s.add(u)
        s.commit()
        return u.id


def _seed_done_audit(app: FastAPI) -> None:
    """A completed audit → PAST the first-run state. During first run the guided
    hero (#4) is the surface and the getting-started checklist is suppressed to
    avoid two competing step-lists; once an audit exists the checklist is the
    active activation tracker again."""
    uid = _user(app)
    with app.state.session_factory() as s:
        s.add(
            Audit(
                user_id=uid,
                status="done",
                observed_days=7,
                total_spend_usd=100.0,
                report_ready_at=utcnow(),
            )
        )
        s.commit()


class TestOnboardingMetric:
    def test_a_fresh_account_has_zero_steps_and_step_one_is_next(self, app: FastAPI) -> None:
        uid = _user(app)
        with app.state.session_factory() as s:
            ob = metrics.onboarding(s, uid)
        assert ob["done"] == 0 and ob["total"] == 5 and not ob["all_done"]
        assert ob["next"]["key"] == "connect"

    def test_steps_self_complete_as_the_customer_progresses(self, app: FastAPI) -> None:
        uid = _user(app)
        with app.state.session_factory() as s:
            s.add(Source(user_id=uid, provider="openai", label="p", credentials_encrypted="x"))
            audit = Audit(user_id=uid, status="done", observed_days=7, total_spend_usd=100.0)
            s.add(audit)
            s.flush()
            s.add(
                FindingRow(
                    audit_id=audit.id,
                    finding_id="D1-001",
                    detector="d1_oversized_model",
                    severity="high",
                    monthly_impact_usd=50.0,
                    confidence="estimated",
                    fix_text="switch model",
                    evidence_sample=[],
                    route="chat",
                )
            )
            s.add(
                FindingFeedback(
                    audit_id=audit.id, finding_id="D1-001", verdict="applied", actor=EMAIL
                )
            )
            s.commit()
            ob = metrics.onboarding(s, uid)
        # connect + audit + review + apply done (4/5); "verified" needs a re-audit
        assert ob["done"] == 4
        assert ob["next"]["key"] == "verified"
        assert [x["key"] for x in ob["steps"] if x["done"]] == [
            "connect",
            "audit",
            "review",
            "apply",
        ]


class TestOnboardingOnDashboard:
    def test_fresh_user_sees_guided_hero_not_checklist(self, app: FastAPI) -> None:
        # First run (no audit): the guided first-run hero (#4) is the surface;
        # the checklist is intentionally suppressed so the two step-lists don't
        # double. (Full first-run coverage in tests/test_guided_first_run.py.)
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert "money hiding in your LLM spend" in page  # the guided hero
        assert "Get to your first verified saving" not in page  # checklist suppressed

    def test_checklist_resumes_after_the_first_audit(self, app: FastAPI) -> None:
        _seed_done_audit(app)  # past first run → the checklist is the surface again
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert "money hiding in your LLM spend" not in page  # first-run hero gone
        assert "Get to your first verified saving" in page  # checklist back, tracking

    def test_hide_suppresses_it_across_the_session(self, app: FastAPI) -> None:
        _seed_done_audit(app)  # the checklist only renders past the first-run state
        client = TestClient(app)
        assert "Get to your first verified saving" in client.get("/dashboard", headers=HDR).text
        resp = client.post("/dashboard/onboarding/hide", headers=HDR, follow_redirects=False)
        assert resp.status_code == 303
        assert "onboarding_hidden=" in resp.headers.get("set-cookie", "")
        # the cookie now suppresses it
        assert "Get to your first verified saving" not in client.get("/dashboard", headers=HDR).text

    def test_it_vanishes_when_every_step_is_done(self, app: FastAPI, monkeypatch) -> None:
        # past first run (a completed audit), all steps done → all_done → not rendered
        _seed_done_audit(app)
        monkeypatch.setattr(
            metrics,
            "onboarding",
            lambda s, uid: {"steps": [], "done": 5, "total": 5, "all_done": True, "next": None},
        )
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert "Get to your first verified saving" not in page


class TestActivityCenter:
    """Wave B — the bell counts what's new; opening the feed clears it."""

    def _seed_audit(self, app: FastAPI) -> str:
        from datetime import UTC, datetime

        with app.state.session_factory() as s:
            u = User(email=EMAIL)
            s.add(u)
            s.flush()
            s.add(
                Audit(
                    user_id=u.id,
                    status="done",
                    row_count=1234,
                    total_spend_usd=500.0,
                    report_ready_at=datetime.now(UTC),
                )
            )
            s.commit()
            return u.id

    def test_bell_badge_and_since_here_appear_for_new_events(self, app: FastAPI) -> None:
        self._seed_audit(app)
        dash = TestClient(app).get("/dashboard", headers=HDR).text
        assert "bell-badge" in dash
        assert "since you were last here" in dash

    def test_the_feed_lists_the_event_and_opening_it_clears_the_badge(self, app: FastAPI) -> None:
        self._seed_audit(app)
        client = TestClient(app)
        assert "bell-badge" in client.get("/dashboard", headers=HDR).text
        feed = client.get("/activity", headers=HDR)
        assert feed.status_code == 200 and "Audit completed" in feed.text
        # opening the feed stamped activity_seen_at → badge gone
        assert "bell-badge" not in client.get("/dashboard", headers=HDR).text

    def test_empty_account_has_no_badge_and_a_designed_empty_feed(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert "bell-badge" not in client.get("/dashboard", headers=HDR).text
        assert "Nothing here yet" in client.get("/activity", headers=HDR).text


class TestActivityHonesty:
    """ux-gate FAIL fix: the feed must NEVER present a self-reported figure as
    a verified saving. An applied fix is an honest 'Fix applied' event whose
    saving is verified only on the next audit."""

    def test_applied_fix_is_not_labeled_verified_and_shows_no_self_reported_dollars(
        self, app: FastAPI
    ) -> None:
        from tokenops_cost_auditor.persistence.models import Audit, FindingFeedback
        from tokenops_cost_auditor.services.dashboard import activity

        with app.state.session_factory() as s:
            u = User(email=EMAIL)
            s.add(u)
            s.flush()
            a = Audit(user_id=u.id, status="done", row_count=10)
            s.add(a)
            s.flush()
            # a customer self-reported $999 saving at apply time
            s.add(
                FindingFeedback(
                    audit_id=a.id,
                    finding_id="D1-001",
                    verdict="applied",
                    savings_realized_usd=999.0,
                    actor=EMAIL,
                )
            )
            s.commit()
            events = activity.recent(s, u.id)
        applied = [e for e in events if e.kind == "applied"]
        assert applied, "an applied fix should surface as an event"
        e = applied[0]
        assert e.title == "Fix applied"
        assert "verified saving" not in (e.title + e.detail).lower()
        assert "$999" not in e.detail and "999" not in e.detail  # never the self-reported number


class TestVerifiedSavingsCelebration:
    """Wave B: the celebration fires ONLY on a genuinely verified saving
    (>$0, re-audit-proven) — honest by construction."""

    def test_no_celebration_without_a_verified_saving(self, app: FastAPI) -> None:
        # a fresh/zero-verified account shows no celebration tag
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert "Real money back" not in page

    def test_celebration_appears_only_when_verified_is_positive(
        self, app: FastAPI, monkeypatch
    ) -> None:
        from tokenops_cost_auditor.services.dashboard.metrics import Widget

        # past the first-run state so the live savings widget renders (first run
        # shows the guided hero instead); then a widget with a real verified
        # figure → celebration. Proves the gate is verified>0, nothing else.
        _seed_done_audit(app)
        monkeypatch.setattr(
            metrics,
            "savings",
            lambda s, uid: (
                Widget(
                    empty=False,
                    provenance="audit x",
                    data={
                        "verified": 250.0,
                        "identified": 0.0,
                        "customer_reported": 0.0,
                        "verified_count": 1,
                        "pending_count": 0,
                    },
                ),
                None,
            ),
        )
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert "Real money back — proven on your own logs" in page


class TestAuditClarity:
    """Founder incident 2026-07-22: a real connected audit whose only model was
    unpriced showed the 'connect a source' empty state. The page must instead
    say WHY it's empty — and never confuse 'no audit' with 'audit ran'."""

    def _connected_unpriced_audit(self, app: FastAPI) -> None:
        from datetime import UTC, date, datetime

        from tokenops_cost_auditor.persistence.models import Audit, Source, SourceUsage

        with app.state.session_factory() as s:
            u = User(email=EMAIL)
            s.add(u)
            s.flush()
            src = Source(user_id=u.id, provider="openai", label="p", credentials_encrypted="x")
            s.add(src)
            s.flush()
            s.add(
                SourceUsage(
                    source_id=src.id,
                    day=date(2026, 6, 30),
                    model="gpt-4o-mini-2024-07-18",  # not on the rate card
                    calls=35,
                    prompt_tokens=16012,
                    completion_tokens=944,
                    cached_tokens=0,
                )
            )
            s.add(
                Audit(
                    user_id=u.id,
                    status="done",
                    row_count=35,
                    total_spend_usd=0,
                    report_ready_at=datetime.now(UTC),
                )
            )
            s.commit()

    def test_metric_reports_unpriced_not_no_audit(self, app: FastAPI) -> None:
        self._connected_unpriced_audit(app)
        with app.state.session_factory() as s:
            c = metrics.audit_clarity(
                s,
                app.state.pricing_table,
                s.execute(metrics.select(User.id).where(User.email == EMAIL)).scalar_one(),
            )
        assert c["state"] == "unpriced"
        assert "gpt-4o-mini-2024-07-18" in c["models"]
        assert c["row_count"] == 35

    def test_findings_explains_unpriced_instead_of_connect(self, app: FastAPI) -> None:
        self._connected_unpriced_audit(app)
        page = TestClient(app).get("/findings", headers=HDR).text
        assert "gpt-4o-mini-2024-07-18" in page
        assert "verified rate card yet" in page
        assert "Run an audit and they appear" not in page  # NOT the no-audit state

    def test_dashboard_banner_explains_unpriced(self, app: FastAPI) -> None:
        self._connected_unpriced_audit(app)
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert "gpt-4o-mini-2024-07-18" in page and "verified rate card yet" in page

    def test_no_audit_still_says_connect(self, app: FastAPI) -> None:
        with app.state.session_factory() as s:
            s.add(User(email=EMAIL))
            s.commit()
        page = TestClient(app).get("/findings", headers=HDR).text
        assert "Connect a source" in page  # genuinely no audit → connect is right
