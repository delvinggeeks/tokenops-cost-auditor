"""Findings clarity — route naming + materiality floor, walked on /findings
(R-VERTICAL, founder 2026-07-25 "work through what is worth fixing").

A real audit runs the full pipeline → the findings page names each finding's route
(so many findings of one kind read as DISTINCT, not identical text) and never shows
a $0.00 savings row (the floor dropped it before persistence).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, FindingRow, User

FIXTURES = Path(__file__).parent / "fixtures"
EMAIL = "clarity@example.com"
HDR = {"X-User-Email": EMAIL}


def _seed_and_run(app: FastAPI, fixture: str) -> str:
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
        audit_id = audit.id
    app.state.runner.run(audit_id)
    return audit_id


class TestFindingsClarityJourney:
    def test_findings_page_names_the_route(self, app: FastAPI, settings: Settings) -> None:
        _seed_and_run(app, "waste_pack_anthropic.jsonl")
        page = TestClient(app).get("/findings", headers=HDR).text
        # the route is rendered next to the plain headline → distinct findings,
        # not seven copies of the same generic text.
        assert "on <code>" in page
        assert "rag-bloated" in page  # a real route named on the list (D3)
        # and no zero-value savings noise reaches the page.
        assert "$0.00" not in page

    def test_floor_drops_savings_noise_before_persistence(
        self, app: FastAPI, settings: Settings
    ) -> None:
        # with a sky-high floor, every SAVINGS finding is dropped in run_all and never
        # persisted — so /findings can never show it. waste_pack_anthropic has no
        # informational finding, so nothing positive-dollar survives.
        app.state.settings.min_finding_monthly_usd = 1e9
        audit_id = _seed_and_run(app, "waste_pack_anthropic.jsonl")
        with app.state.session_factory() as session:
            rows = list(
                session.execute(select(FindingRow).where(FindingRow.audit_id == audit_id))
                .scalars()
                .all()
            )
        assert all(r.monthly_impact_usd == 0.0 for r in rows)  # no savings persisted
