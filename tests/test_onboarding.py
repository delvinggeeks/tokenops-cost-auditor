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
    def test_fresh_user_sees_the_checklist(self, app: FastAPI) -> None:
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert "Get to your first verified saving" in page
        assert "0 of 5 done" in page

    def test_hide_suppresses_it_across_the_session(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert "Get to your first verified saving" in client.get("/dashboard", headers=HDR).text
        resp = client.post("/dashboard/onboarding/hide", headers=HDR, follow_redirects=False)
        assert resp.status_code == 303
        assert "onboarding_hidden=" in resp.headers.get("set-cookie", "")
        # the cookie now suppresses it
        assert (
            "Get to your first verified saving" not in client.get("/dashboard", headers=HDR).text
        )

    def test_it_vanishes_when_every_step_is_done(self, app: FastAPI, monkeypatch) -> None:
        # a completed account (all steps done) → all_done → not rendered
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
