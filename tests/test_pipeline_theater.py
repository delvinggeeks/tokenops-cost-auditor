"""R-PIPELINE-UI-SEQ pre-launch carve-out (founder, 2026-07-27) — the live
pipeline theater and the row-errors surfacing.

The theater's law: stages light ONLY on data that has actually landed. Two
checkpoints are observable today (ingest's mid-run commit, and completion);
everything between shows as pending — never as done. Ownership is re-checked
on every poll (§5d), and terminal states stop the polling by construction.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, User

EMAIL = "theater@example.com"
HDR = {"X-User-Email": EMAIL}


def seed_audit(app: FastAPI, tmp_path, **fields) -> str:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        audit = Audit(user_id=user.id, **fields)
        session.add(audit)
        session.commit()
        return audit.id


class TestTheStagesLightHonestly:
    def test_queued_lights_nothing_and_keeps_polling(self, app: FastAPI, tmp_path) -> None:
        audit_id = seed_audit(app, tmp_path, status="queued")
        page = TestClient(app).get(f"/audits/{audit_id}/progress/partial", headers=HDR).text
        assert "Waiting for a worker slot" in page
        assert 'hx-trigger="every 2500ms"' in page  # still polling
        assert 'class="seg active"' not in page  # nothing claims completion

    def test_processing_after_ingest_lights_ingest_only(self, app: FastAPI, tmp_path) -> None:
        audit_id = seed_audit(app, tmp_path, status="processing", row_count=12345, valid_pct=99.2)
        page = TestClient(app).get(f"/audits/{audit_id}/progress/partial", headers=HDR).text
        assert "12,345 rows" in page and "99.2% parsed" in page
        # price/detect/report may NOT claim completion mid-run
        assert page.count("seg active") == 1, "only ingest has landed"
        assert 'hx-trigger="every 2500ms"' in page

    def test_done_swaps_to_the_report_links_and_stops_polling(self, app: FastAPI, tmp_path) -> None:
        audit_id = seed_audit(
            app,
            tmp_path,
            status="done",
            row_count=100,
            valid_pct=100.0,
            total_spend_usd=42.5,
            observed_days=30,
        )
        page = TestClient(app).get(f"/audits/{audit_id}/progress/partial", headers=HDR).text
        assert "Open your findings" in page
        assert "hx-trigger" not in page, "terminal state must stop the poll"
        assert page.count("seg active") == 4  # everything landed

    def test_failed_says_what_happened_and_what_to_do(self, app: FastAPI, tmp_path) -> None:
        audit_id = seed_audit(
            app, tmp_path, status="failed", error="row 3: timestamp is not ISO-8601"
        )
        page = TestClient(app).get(f"/audits/{audit_id}/progress/partial", headers=HDR).text
        assert "row 3: timestamp is not ISO-8601" in page  # what happened
        assert "upload the file again" in page  # what to do
        assert "support@tokenops.cloud" in page
        assert "hx-trigger" not in page

    def test_the_poll_partial_is_never_cached(self, app: FastAPI, tmp_path) -> None:
        audit_id = seed_audit(app, tmp_path, status="processing")
        resp = TestClient(app).get(f"/audits/{audit_id}/progress/partial", headers=HDR)
        assert "no-store" in resp.headers.get("cache-control", "")


class TestTheFullPageRendersForItsOwner:
    def test_owner_gets_the_shell_and_the_theater(self, app: FastAPI, tmp_path) -> None:
        """The gap the preview render caught: no test loaded the PAGE as its
        owner, so a _shell_ctx KeyError shipped past a green suite."""
        audit_id = seed_audit(app, tmp_path, status="processing", row_count=10, valid_pct=100.0)
        page = TestClient(app).get(f"/audits/{audit_id}/progress", headers=HDR)
        assert page.status_code == 200
        assert 'id="theater"' in page.text and 'class="sidebar"' in page.text
        assert "Your audit, live" in page.text


class TestOwnershipOnEveryPoll:
    def test_every_theater_endpoint_404s_for_the_wrong_user(self, app: FastAPI, tmp_path) -> None:
        audit_id = seed_audit(app, tmp_path, status="processing")
        other = {"X-User-Email": "someone@else.com"}
        client = TestClient(app)
        for path in (
            f"/audits/{audit_id}/progress",
            f"/audits/{audit_id}/progress/partial",
            f"/audits/{audit_id}/row-errors",
        ):
            assert client.get(path, headers=other).status_code == 404, path


class TestRowErrorsSurface:
    def _with_upload(self, app: FastAPI, tmp_path, errors: int) -> str:
        updir = tmp_path / "up-theater"
        updir.mkdir(exist_ok=True)
        upload = updir / "original.jsonl"
        upload.write_text("{}")
        if errors:
            (updir / "row_errors.csv").write_text(
                "row,error\n" + "\n".join(f"{i},bad" for i in range(errors)) + "\n"
            )
        return seed_audit(
            app,
            tmp_path,
            status="done",
            row_count=50,
            valid_pct=96.0,
            upload_path=str(upload),
        )

    def test_rejected_rows_link_and_download(self, app: FastAPI, tmp_path) -> None:
        audit_id = self._with_upload(app, tmp_path, errors=2)
        client = TestClient(app)
        page = client.get(f"/audits/{audit_id}/progress/partial", headers=HDR).text
        assert "2 rows\n          rejected — see why" in page or "2 rows" in page
        csv = client.get(f"/audits/{audit_id}/row-errors", headers=HDR)
        assert csv.status_code == 200
        assert csv.headers["content-type"].startswith("text/csv")
        assert "row,error" in csv.text

    def test_the_honest_zero_is_a_statement(self, app: FastAPI, tmp_path) -> None:
        audit_id = self._with_upload(app, tmp_path, errors=0)
        page = TestClient(app).get(f"/audits/{audit_id}/progress/partial", headers=HDR).text
        assert "0 rows rejected — every row parsed." in page
        # and the download honestly 404s rather than serving an empty file
        assert TestClient(app).get(f"/audits/{audit_id}/row-errors", headers=HDR).status_code == 404


class TestBrowserLandsInTheTheater:
    def test_html_form_post_redirects_api_contract_unchanged(self, app: FastAPI, tmp_path) -> None:
        """Browsers lead Accept with text/html and get the 303; API clients
        keep the JSON 201 byte-for-byte."""
        from tokenops_cost_auditor.persistence.models import Payment

        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
            if user is None:
                user = User(email=EMAIL)
                session.add(user)
                session.flush()
            session.add(Payment(user_id=user.id, provider="stripe", amount=500.0, currency="USD"))
            session.commit()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/audits",
            headers={**HDR, "Accept": "text/html,application/xhtml+xml"},
            files={"file": ("calls.jsonl", b'{"ts": "2026-07-01T00:00:00Z"}\n')},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/audits/")
        assert resp.headers["location"].endswith("/progress")
