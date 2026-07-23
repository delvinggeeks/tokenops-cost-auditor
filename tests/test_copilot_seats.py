"""WP-COPILOT-AGG tests (R-COPILOT) — seat governance.

The load-bearing pins: FR-22 (dates only, never a login/content — even when
the export CARRIES logins), the idle-seat analysis, the rate-is-an-input
honesty (R-COPILOT P1), and the upload→report journey (the seat finding
lands in the report, labeled seat governance, X-02 observe-only).
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, FindingRow
from tokenops_cost_auditor.services.copilot.seats import (
    SeatRecord,
    analyze,
    build_finding,
    parse_seats,
)

EMAIL = "copilot-owner@example.com"
HDR = {"X-User-Email": EMAIL}
NOW = datetime(2026, 7, 24, tzinfo=UTC)


def seats_json(active: int, idle: int, never: int) -> str:
    recent = (NOW - timedelta(days=2)).isoformat()
    stale = (NOW - timedelta(days=90)).isoformat()
    seats = []
    for _ in range(active):
        seats.append(
            {
                "assignee": {"login": "SECRET-USERNAME"},
                "last_activity_at": recent,
                "created_at": recent,
            }
        )
    for _ in range(idle):
        seats.append(
            {
                "assignee": {"login": "SECRET-USERNAME"},
                "last_activity_at": stale,
                "created_at": stale,
            }
        )
    for _ in range(never):
        seats.append(
            {
                "assignee": {"login": "SECRET-USERNAME"},
                "last_activity_at": None,
                "created_at": stale,
            }
        )
    return json.dumps({"total_seats": len(seats), "seats": seats})


class TestFR22AndParse:
    def test_01_logins_never_parsed_even_when_present(self) -> None:
        recs = parse_seats(seats_json(active=1, idle=1, never=0))
        # SeatRecord has NO login field — the type itself forbids it
        assert all(isinstance(r, SeatRecord) for r in recs)
        assert not any(hasattr(r, "login") or hasattr(r, "assignee") for r in recs)
        # and the export's login text never survives into a record
        assert "SECRET" not in str([r.__dict__ for r in recs])

    def test_02_csv_shape_accepted(self) -> None:
        csv = "last_activity_at,created_at,pending_cancellation\n"
        csv += f"{(NOW - timedelta(days=90)).isoformat()},{NOW.isoformat()},false\n"
        csv += f",{NOW.isoformat()},false\n"  # never-used
        recs = parse_seats(csv)
        assert len(recs) == 2 and recs[1].last_activity_at is None

    def test_03_malformed_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            parse_seats('{"seats": []}')
        with pytest.raises(ValueError):
            parse_seats("not json, not csv header")


class TestAnalysis:
    def test_04_idle_counts_and_recoverable(self) -> None:
        recs = parse_seats(seats_json(active=6, idle=3, never=1))  # 4 idle total
        s = analyze(recs, idle_days=30, rate_usd=19.0, now=NOW)
        assert s.total == 10 and s.idle == 4 and s.never_used == 1 and s.active == 6
        assert s.monthly_recoverable_usd == 4 * 19.0

    def test_05_finding_is_labeled_seat_governance_rate_is_input(self) -> None:
        recs = parse_seats(seats_json(active=6, idle=4, never=0))
        f = build_finding(analyze(recs, now=NOW))
        assert f.detector == "d7_idle_seats"  # not a token detector id
        assert f.detail is not None and f.detail["kind"] == "seat_governance"
        assert f.detail["rate_is_input"] is True  # R-COPILOT P1: not a verified rate
        assert "confirm it" in f.fix_text and "$19" in f.fix_text
        assert f.evidence == ()  # no per-seat evidence rows — counts only


class TestJourney:
    def test_06_upload_lands_a_seat_report(self, app: FastAPI) -> None:
        """The DoD: upload a seats export → the seat finding lands in a report,
        reachable at the signed URL, labeled seat governance."""
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)  # create the account
        blob = seats_json(active=40, idle=10, never=2).encode()
        resp = client.post(
            "/copilot/seats",
            files={"file": ("seats.json", io.BytesIO(blob), "application/json")},
            data={"idle_days": "30", "rate_usd": "19"},
            headers=HDR,
            follow_redirects=False,
        )
        assert resp.status_code == 303 and resp.headers["location"].startswith("/r/")
        # the report page renders and shows the seat finding, not token waste
        report = client.get(resp.headers["location"])
        assert report.status_code == 200
        with app.state.session_factory() as session:
            audit = session.execute(
                select(Audit).where(Audit.provider_mix == "github-copilot")
            ).scalar_one()
            assert audit.status == "done" and audit.paid_via == "copilot-seats"
            fr = session.execute(select(FindingRow)).scalars().all()
            assert len(fr) == 1 and fr[0].detector == "d7_idle_seats"
            # 12 idle (10 stale + 2 never) at $19/seat
            assert abs(float(fr[0].monthly_impact_usd) - 12 * 19.0) < 0.01
            # FR-22: the stored file carries no username
            assert audit.upload_path is None  # seat audits store no raw upload

    def test_07_form_reachable_on_upload_page(self, app: FastAPI) -> None:
        html = TestClient(app).get("/upload", headers=HDR).text
        assert 'action="/copilot/seats"' in html  # the click path exists
        assert "never a username" in html  # the FR-22 promise, stated at the door

    def test_08_malformed_upload_is_a_clean_400(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)
        resp = client.post(
            "/copilot/seats",
            files={"file": ("x.json", io.BytesIO(b'{"seats":[]}'), "application/json")},
            headers=HDR,
        )
        assert resp.status_code == 400
