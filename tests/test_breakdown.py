"""Tokenomics breakdown — enterprise depth engine, slice 1 (founder 2026-07-25).

Walks the whole journey (R-VERTICAL, ship=walk): a real audit runs the full
pipeline → the runner writes an EXACT tokenomics.json artifact → the /breakdown
page renders the vitals, per-model and per-route (cost-allocation) tables, and the
data-coverage — all reachable from the shell nav. Honest empty state when there
is no audit yet.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, User
from tokenops_cost_auditor.services.runner import AuditRunner

FIXTURES = Path(__file__).parent / "fixtures"
EMAIL = "breakdown@example.com"
HDR = {"X-User-Email": EMAIL}


def _seed_audit(app: FastAPI, fixture: str) -> str:
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == EMAIL)) or User(email=EMAIL)
        session.add(user)
        session.flush()
        audit = Audit(user_id=user.id, status="queued")
        session.add(audit)
        session.flush()
        upload_dir = Path(app.state.settings.upload_dir) / audit.id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"original{Path(fixture).suffix}"
        shutil.copyfile(FIXTURES / fixture, dest)
        audit.upload_path = str(dest)
        session.commit()
        return audit.id


class TestBreakdownJourney:
    def test_audit_produces_exact_breakdown_and_it_renders(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        runner: AuditRunner = app.state.runner
        runner.run(audit_id)

        # the runner wrote the deterministic tokenomics artifact next to the report
        tk_path = Path(settings.report_dir) / audit_id / "tokenomics.json"
        assert tk_path.exists(), "runner did not write tokenomics.json"
        tk = json.loads(tk_path.read_text(encoding="utf-8"))
        assert tk["monthly_spend_usd"] > 0
        assert tk["by_model"] and tk["by_route"]
        assert 0.0 <= tk["cache_hit_rate"] <= 1.0
        assert tk["pct_priced"] == 1.0  # the sample is fully priced

        # FR-36 behaviour lens: one shape per route, keyed like by_route
        assert set(tk["route_shapes"]) == {s["name"] for s in tk["by_route"]}
        summarizer = tk["route_shapes"]["summarizer"]
        assert summarizer["cls"] == "agent_loop"
        assert "repeated input signature" in summarizer["rationale"]

        # and it renders on /breakdown with the exact slices + the shape chips
        page = TestClient(app).get("/breakdown", headers=HDR).text
        assert "Tokenomics vitals" in page
        assert "By model" in page and "By route (cost allocation)" in page
        assert "Data coverage" in page
        assert tk["by_model"][0]["name"] in page  # the top model appears in the table
        assert "Workload shape by route" in page
        assert "Agent loop" in page  # the summarizer/agent-7 routes' chip label
        assert "repeated input signature seen 30 times" in page  # counts-citing rationale

    def test_corrupt_artifact_degrades_to_empty_state_not_500(
        self, app: FastAPI, settings: Settings
    ) -> None:
        # a partial/corrupt tokenomics.json (crash mid-write) must not 500 the page
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        (Path(settings.report_dir) / audit_id / "tokenomics.json").write_text(
            "{ this is not valid json", encoding="utf-8"
        )
        resp = TestClient(app).get("/breakdown", headers=HDR)
        assert resp.status_code == 200  # not a 500
        assert "No breakdown yet" in resp.text  # honest empty state

    def test_no_audit_shows_honest_empty_state(self, app: FastAPI) -> None:
        page = TestClient(app).get("/breakdown", headers=HDR)
        assert page.status_code == 200
        assert "No breakdown yet" in page.text
        assert "$0.00" not in page.text  # never a fabricated breakdown

    def test_breakdown_is_reachable_from_the_shell_nav(self, app: FastAPI) -> None:
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert 'href="/breakdown"' in page
