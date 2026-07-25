"""Spend anomaly (D10) — deterministic "dynamic analysis based on logs", walked
end-to-end (R-VERTICAL, ship=walk).

A real audit over a >=7-day log with one spike day runs the FULL pipeline → D10
produces a finding → it is reachable on /findings with plain-English for BOTH
audiences → the drawer renders the human summary AND the technical pointers
(detector id, rendered thresholds, the spike day, the driver, counts-only
evidence). Honestly DORMANT on a short (sub-week) log: no fabricated spike.
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
EMAIL = "anomaly@example.com"
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


def _run(app: FastAPI, fixture: str) -> str:
    audit_id = _seed_audit(app, fixture)
    app.state.runner.run(audit_id)
    return audit_id


def _d10_rows(app: FastAPI, audit_id: str) -> list[FindingRow]:
    with app.state.session_factory() as session:
        return list(
            session.execute(
                select(FindingRow).where(
                    FindingRow.audit_id == audit_id,
                    FindingRow.detector == "d10_spend_anomaly",
                )
            )
            .scalars()
            .all()
        )


class TestSpendAnomalyJourney:
    def test_spike_log_produces_reachable_plain_english_finding(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _run(app, "spend_spike.csv")

        rows = _d10_rows(app, audit_id)
        assert len(rows) == 1, "the spike day must surface exactly one anomaly finding"
        row = rows[0]
        assert row.monthly_impact_usd == 0.0  # informational — no claimed saving
        fid = row.finding_id

        # reachable on /findings: plain headline + plain-English summary + a click
        # path to the drawer (apostrophes HTML-escape, so assert apostrophe-free).
        client = TestClient(app)
        page = client.get("/findings", headers=HDR).text
        assert "spend spiked far above your normal" in page
        assert "jumped well above what you normally spend in a day" in page
        assert f"/findings/{audit_id}/{fid}" in page  # the Details button target

        # the drawer answers for BOTH audiences: human summary AND technical pointers
        drawer = client.get(f"/findings/{audit_id}/{fid}", headers=HDR)
        assert drawer.status_code == 200
        d = drawer.text
        assert "spend spiked far above your normal" in d  # plain headline (h2)
        assert "jumped well above what you normally spend in a day" in d  # summary
        assert "d10_spend_anomaly" in d  # technical: the detector id
        assert "D10 spend anomaly" in d  # technical: the label
        assert "MADs above your median" in d  # thresholds rendered from live settings
        assert "2026-07-08" in d  # the specific spike day, from the finding
        assert "claude-opus-4-8" in d  # the driver model, named
        assert "spend spike" in d  # counts-only evidence note (FR-22)
        # informational finding: an honest "Informational" chip, never a misleading
        # $0.00 in the waste colour (ux gate 2026-07-25)
        assert "Informational" in d and "$0.00" not in d

    def test_short_log_is_honestly_dormant(self, app: FastAPI) -> None:
        # the committed waste_pack spans 3 days — below the weekly baseline, so
        # D10 stays silent rather than call a spike on too little history.
        audit_id = _run(app, "waste_pack_anthropic.jsonl")
        assert _d10_rows(app, audit_id) == []
