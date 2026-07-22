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
        assert resp.status_code == 303 and "onboarding_hidden=" in resp.headers.get("set-cookie", "")
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
