"""FR-37 acceptance journey (T-F4, Issue #102) — upload → finding → apply →
re-audit → statement, walked end-to-end (R-VERTICAL, ship=walk).

TWO real audits run the full pipeline on the fr37 fixture pair: the SAME
claude-sonnet-5 route, uncached June waste then cache-fixed July traffic —
the only fixtures spanning >= MIN_VERIFY_DAYS observed days, so the July
audit genuinely QUALIFIES as verification (the waste packs span 3 days and
never can). The customer applies the D2 finding through the real feedback
route; the July statement is issued through the real send route and must
show the attributed verified line with BOTH audit ids (R-Q9 provenance).

Figures are asserted LIVE against compute() — exact values belong to the
money-math goldens (test_verified_savings/test_statements); the journey owns
the click path and the attribution plumbing between the layers.
"""

from __future__ import annotations

import html
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, FindingFeedback, FindingRow, User
from tokenops_cost_auditor.services.dashboard.savings import compute
from tokenops_cost_auditor.services.rules.detector_copy import DETECTOR_COPY

FIXTURES = Path(__file__).parent / "fixtures"
EMAIL = "fr37@example.com"
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


class TestFr37Journey:
    def test_apply_reaudit_statement_shows_attributed_verified_line(self, app: FastAPI) -> None:
        client = TestClient(app)

        # 1. UPLOAD: the June audit runs the real pipeline and raises the
        #    D2 finding on the sonnet route (8 observed days).
        audit_a = _seed_and_run(app, "fr37_before.jsonl", datetime(2026, 6, 8, 20, tzinfo=UTC))
        with app.state.session_factory() as session:
            d2 = session.execute(
                select(FindingRow).where(
                    FindingRow.audit_id == audit_a,
                    FindingRow.detector == "d2_missing_cache",
                )
            ).scalar_one()
            assert d2.route == "claude-sonnet-5"
            assert float(d2.monthly_impact_usd) > 0
            fid = d2.finding_id
            a_obs = session.get(Audit, audit_a)
            assert a_obs is not None and (a_obs.observed_days or 0) >= 7

        # 2. APPLY: the customer records the verdict through the real route.
        r = client.post(
            f"/findings/{audit_a}/{fid}/feedback", data={"verdict": "applied"}, headers=HDR
        )
        assert r.status_code == 200, r.text
        # Deterministic clock plumbing (same class as the seeded created_at):
        # the fix was applied 2026-06-20, between the two audits.
        with app.state.session_factory() as session:
            fb = session.execute(
                select(FindingFeedback).where(
                    FindingFeedback.audit_id == audit_a, FindingFeedback.finding_id == fid
                )
            ).scalar_one()
            assert fb.verdict == "applied"
            fb.ts = datetime(2026, 6, 20, 12, tzinfo=UTC)
            session.commit()

        # 3. RE-AUDIT: July traffic on the SAME route, cache fixed — the
        #    qualifying (>=7-day, post-apply) audit that proves the saving.
        audit_b = _seed_and_run(app, "fr37_after.jsonl", datetime(2026, 7, 8, 20, tzinfo=UTC))
        with app.state.session_factory() as session:
            still_d2 = session.execute(
                select(FindingRow).where(
                    FindingRow.audit_id == audit_b,
                    FindingRow.detector == "d2_missing_cache",
                )
            ).scalar_one_or_none()
            assert still_d2 is None, "the fixed route must not re-raise D2"
            user = session.scalar(select(User).where(User.email == EMAIL))
            assert user is not None
            summary = compute(session, user.id, period=(2026, 7))

        # The emission itself: one line, full provenance, sum == headline.
        assert summary.verified_usd > 0
        assert len(summary.verified_lines) == 1
        line = summary.verified_lines[0]
        assert line.finding_ref == fid
        assert line.detector == "d2_missing_cache"
        assert line.from_audit == audit_a
        assert line.to_audit == audit_b
        assert round(sum(vl.amount_usd for vl in summary.verified_lines), 2) == (
            summary.verified_usd
        )

        # 4. STATEMENT: issued through the real click (send → detail page).
        r = client.post("/statements/2026-07/send", headers=HDR, follow_redirects=False)
        assert r.status_code == 303, r.text
        page = client.get("/statements/2026-07", headers=HDR)
        assert page.status_code == 200
        body = html.unescape(page.text)  # the plain copy's apostrophe renders as &#39;
        assert f"VERIFIED SAVINGS THIS MONTH: ${summary.verified_usd:,.2f}" in body
        # The attributed line: plain-language lead (ux jargon law) + the ref
        # + BOTH short audit-id stamps (R-Q9 provenance).
        assert DETECTOR_COPY["d2_missing_cache"]["plain"] in body
        assert (
            f"(ref {fid}, raised in audit {audit_a[:4]}…{audit_a[-3:]}, "
            f"proved by audit {audit_b[:4]}…{audit_b[-3:]})"
        ) in body

    def test_unproven_apply_shows_no_attributed_line(self, app: FastAPI) -> None:
        """Honest state: applied but not yet re-audited → pending, no line,
        no scaffolding — the June statement's VERIFIED section is unchanged."""
        client = TestClient(app)
        audit_a = _seed_and_run(app, "fr37_before.jsonl", datetime(2026, 6, 8, 20, tzinfo=UTC))
        with app.state.session_factory() as session:
            d2 = session.execute(
                select(FindingRow).where(
                    FindingRow.audit_id == audit_a,
                    FindingRow.detector == "d2_missing_cache",
                )
            ).scalar_one()
            fid = d2.finding_id
        r = client.post(
            f"/findings/{audit_a}/{fid}/feedback", data={"verdict": "applied"}, headers=HDR
        )
        assert r.status_code == 200, r.text
        with app.state.session_factory() as session:
            fb = session.execute(
                select(FindingFeedback).where(
                    FindingFeedback.audit_id == audit_a, FindingFeedback.finding_id == fid
                )
            ).scalar_one()
            fb.ts = datetime(2026, 6, 20, 12, tzinfo=UTC)
            session.commit()
            user = session.scalar(select(User).where(User.email == EMAIL))
            assert user is not None
            summary = compute(session, user.id, period=(2026, 6))
        assert summary.verified_lines == ()
        assert summary.pending_count == 1
        r = client.post("/statements/2026-06/send", headers=HDR, follow_redirects=False)
        assert r.status_code == 303, r.text
        body = client.get("/statements/2026-06", headers=HDR).text
        assert "VERIFIED SAVINGS THIS MONTH: none yet" in body
        assert "raised in audit" not in body  # no line scaffolding on the zero state
        assert "awaiting confirmation" in body  # the pending fix is named honestly
