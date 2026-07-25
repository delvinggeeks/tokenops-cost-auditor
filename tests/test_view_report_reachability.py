"""ROADMAP §3 #2 — View-report reachability (R-REACHABILITY). Reports used to be
reachable ONLY via the emailed signed link; a customer who closed the email had no
in-app way back. This walks the fix as a user: Runs ledger → 'View report' → the
report renders — and pins the ownership scoping (a foreign / not-done audit 404s)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.persistence.models import utcnow
from tokenops_cost_auditor.persistence.repo import (
    create_audit,
    get_or_create_user,
    get_or_create_workspace,
)

USER = "report-owner@example.com"
STRANGER = "report-stranger@example.com"
HDR = {"X-User-Email": USER}


def _seed_done_audit(app: FastAPI, *, status: str = "done") -> str:
    """A done audit owned by USER, with its rendered report.html on disk (the
    artifact the /r/{token} page serves)."""
    with app.state.session_factory() as s:
        user = get_or_create_user(s, USER)
        get_or_create_workspace(s, user)  # owner workspace, so create_audit can stamp it
        audit = create_audit(s, user.id)
        audit.status = status
        if status == "done":
            audit.report_ready_at = utcnow()
        s.commit()
        aid = audit.id
    if status == "done":
        report_dir = Path(app.state.settings.report_dir) / aid
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.html").write_text(
            f"<h1>Cost audit report {aid}</h1>", encoding="utf-8"
        )
    return aid


class TestReportReachableInApp:
    def test_runs_ledger_links_to_the_report(self, app: FastAPI) -> None:
        aid = _seed_done_audit(app)
        runs = TestClient(app).get("/runs", headers=HDR).text
        assert f"/audits/{aid}/report" in runs  # the affordance is on the ledger
        assert "View report" in runs

    def test_click_through_lands_on_the_rendered_report(self, app: FastAPI) -> None:
        aid = _seed_done_audit(app)
        c = TestClient(app)
        r = c.get(f"/audits/{aid}/report", headers=HDR, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/r/")
        # the fresh signed link renders the report — one report path, reached in-app
        page = c.get(r.headers["location"])
        assert page.status_code == 200 and aid in page.text


class TestReportOwnershipScoping:
    def test_a_stranger_cannot_reach_someone_elses_report(self, app: FastAPI) -> None:
        aid = _seed_done_audit(app)
        r = TestClient(app).get(
            f"/audits/{aid}/report",
            headers={"X-User-Email": STRANGER},
            follow_redirects=False,
        )
        assert r.status_code == 404  # foreign audit — no cross-tenant leak

    def test_an_audit_without_a_report_yet_404s(self, app: FastAPI) -> None:
        aid = _seed_done_audit(app, status="queued")
        r = TestClient(app).get(f"/audits/{aid}/report", headers=HDR, follow_redirects=False)
        assert r.status_code == 404  # not done → no report

    def test_unknown_audit_id_404s(self, app: FastAPI) -> None:
        r = TestClient(app).get("/audits/nope-not-real/report", headers=HDR, follow_redirects=False)
        assert r.status_code == 404
