"""Cross-audit efficiency drift — the Breakdown "vs your last audit" trend, walked
end-to-end (R-VERTICAL, ship=walk).

TWO real audits run the full pipeline → each writes its exact tokenomics.json →
/breakdown renders the trend table comparing this audit to the prior one, with the
regression callout when unit economics slip. A SINGLE audit shows the honest
"run another audit" state — never half a comparison.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, User

FIXTURES = Path(__file__).parent / "fixtures"
EMAIL = "drift@example.com"
HDR = {"X-User-Email": EMAIL}


def _seed_and_run(app: FastAPI, fixture: str, created_at: datetime) -> str:
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == EMAIL)) or User(email=EMAIL)
        session.add(user)
        session.flush()
        audit = Audit(user_id=user.id, status="queued", created_at=created_at)
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


class TestDriftJourney:
    def test_two_audits_render_the_trend_and_regression_callout(
        self, app: FastAPI, settings: Settings
    ) -> None:
        # prior audit: efficient (haiku, high cache). current: worse (opus, low cache).
        _seed_and_run(app, "drift_prior.csv", datetime(2026, 7, 1, 9, tzinfo=UTC))
        _seed_and_run(app, "drift_current.csv", datetime(2026, 7, 10, 9, tzinfo=UTC))

        page = TestClient(app).get("/breakdown", headers=HDR).text
        assert "Trend vs your last audit" in page
        # the efficiency metrics regressed → the honest slipping callout fires
        assert "unit economics are slipping" in page
        assert "Cost per 1K output tokens" in page and "Cache hit rate" in page
        assert "worse" in page  # a judged regression is shown
        # monthly spend is context, never labelled a regression
        assert "Monthly spend" in page

    def test_single_audit_shows_honest_run_another_state(self, app: FastAPI) -> None:
        _seed_and_run(app, "drift_prior.csv", datetime(2026, 7, 1, 9, tzinfo=UTC))
        page = TestClient(app).get("/breakdown", headers=HDR).text
        # only one audit → no fabricated trend, an honest forward-looking prompt
        assert "Trend vs your last audit" not in page
        assert "Run another audit" in page

    def test_partial_prior_artifact_degrades_to_no_trend_not_500(
        self, app: FastAPI, settings: Settings
    ) -> None:
        # a valid-JSON but INCOMPLETE prior tokenomics.json (older schema / partial
        # write) must degrade to no-trend, never a 500.
        _seed_and_run(app, "drift_prior.csv", datetime(2026, 7, 1, 9, tzinfo=UTC))
        _seed_and_run(app, "drift_current.csv", datetime(2026, 7, 10, 9, tzinfo=UTC))
        with app.state.session_factory() as session:
            audits = list(
                session.execute(
                    select(Audit).where(Audit.status == "done").order_by(Audit.created_at.desc())
                )
                .scalars()
                .all()
            )
        prior_id = audits[1].id  # the older (2026-07-01) audit
        (Path(settings.report_dir) / prior_id / "tokenomics.json").write_text(
            '{"monthly_spend_usd": 1.0}', encoding="utf-8"
        )
        resp = TestClient(app).get("/breakdown", headers=HDR)
        assert resp.status_code == 200  # not a 500
        assert "Trend vs your last audit" not in resp.text  # no trend from a broken artifact

    def test_trend_is_workspace_scoped_no_cross_tenant_leak(self, app: FastAPI) -> None:
        # user A has a two-audit trend in their workspace...
        _seed_and_run(app, "drift_prior.csv", datetime(2026, 7, 1, 9, tzinfo=UTC))
        _seed_and_run(app, "drift_current.csv", datetime(2026, 7, 10, 9, tzinfo=UTC))
        # ...user B (their own workspace-of-one, no audits) must NOT see A's trend.
        other = {"X-User-Email": "other-drift@example.com"}
        page = TestClient(app).get("/breakdown", headers=other).text
        assert "Trend vs your last audit" not in page
        assert "unit economics are slipping" not in page  # no leak of A's regression
        assert "No breakdown yet" in page  # B sees only their own honest empty state
