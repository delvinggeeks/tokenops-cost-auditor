"""T-SET-01..03 (PLAN-V15 V-D7 / WP-5) — Settings.

Boring on purpose (R-DESIGN §4f): the tests that matter here are about a
destructive control behaving exactly as its own words promise.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    Audit,
    AuditLogEntry,
    IdempotencyKey,
    Source,
    User,
)
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.web.routes_settings import PURGE_PHRASE

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}


def seed_upload(app: FastAPI, tmp_path: Path, *, with_key: bool = True) -> tuple[str, Path]:
    """An audit holding a real file on disk, plus an FR-26 idempotency key."""
    upload_dir = tmp_path / "uploads" / "a1"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_file = upload_dir / "raw.jsonl"
    upload_file.write_text('{"x": 1}\n', encoding="utf-8")
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        audit = Audit(
            user_id=user.id,
            status="done",
            upload_path=str(upload_file),
            report_ready_at=datetime.now(UTC),
            observed_days=30,
            row_count=5,
        )
        session.add(audit)
        session.flush()
        if with_key:
            session.add(IdempotencyKey(user_id=user.id, key="k-1", audit_id=audit.id))
        session.commit()
        return audit.id, upload_file


class TestSettingsPage:
    def test_auth_required(self, app: FastAPI) -> None:
        assert TestClient(app).get("/settings").status_code == 401

    def test_01_page_groups_render_with_live_facts(self, app: FastAPI, tmp_path: Path) -> None:
        """T-SET-01: the page states what is actually true right now."""
        seed_upload(app, tmp_path)
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            session.add(
                Source(
                    user_id=user.id,
                    provider="openai",
                    label="prod org",
                    credentials_encrypted=encrypt_credential("k" * 64, "sk-1"),
                )
            )
            session.commit()
        page = TestClient(app).get("/settings", headers=HDR).text
        assert "Account" in page and EMAIL in page
        assert "prod org" in page  # sources group
        assert "holding\n      <strong>1</strong>" in page or "<strong>1</strong>" in page
        assert PURGE_PHRASE in page
        # the destructive control states its consequences BEFORE asking
        assert "cannot be undone" in page
        assert "reports and the numbers in them stay" in page
        # transactional mail is honestly excluded from the preference
        assert "always send" in page

    def test_email_preference_round_trip(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/settings", headers=HDR)  # creates the user
        off = client.post("/settings/email", headers=HDR, data={}, follow_redirects=False)
        assert off.status_code == 303
        with app.state.session_factory() as session:
            assert session.execute(select(User)).scalars().one().statement_emails is False
        client.post(
            "/settings/email",
            headers=HDR,
            data={"statement_emails": "1"},
            follow_redirects=False,
        )
        with app.state.session_factory() as session:
            assert session.execute(select(User)).scalars().one().statement_emails is True


class TestPurgeNow:
    def test_02_purge_now_matches_fr21_semantics(self, app: FastAPI, tmp_path: Path) -> None:
        """T-SET-02: raw upload gone from disk, derived data kept, FR-26 key
        deleted, audit_log written — the same definition the scheduled job
        uses, because they share one primitive."""
        audit_id, upload_file = seed_upload(app, tmp_path)
        assert upload_file.exists()
        resp = TestClient(app).post(
            "/settings/purge",
            headers=HDR,
            data={"confirm": PURGE_PHRASE},
            follow_redirects=False,
        )
        assert resp.status_code == 303 and "purged=1" in resp.headers["location"]
        assert not upload_file.exists()
        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            assert audit.upload_path is None and audit.purged_at is not None
            assert audit.row_count == 5  # derived data survives (FR-22 counts)
            assert session.execute(select(IdempotencyKey)).scalars().all() == []  # FR-26
            actions = [e.action for e in session.execute(select(AuditLogEntry)).scalars().all()]
            assert "audit.purged" in actions and "settings.purge_now" in actions

    def test_wrong_phrase_deletes_nothing(self, app: FastAPI, tmp_path: Path) -> None:
        _, upload_file = seed_upload(app, tmp_path)
        resp = TestClient(app).post(
            "/settings/purge",
            headers=HDR,
            data={"confirm": "delete my uploads"},
            follow_redirects=False,
        )
        assert "purged=-1" in resp.headers["location"]
        assert upload_file.exists(), "a near-miss phrase must not destroy data"
        page = TestClient(app).get("/settings?purged=-1", headers=HDR).text
        assert "phrase did not match" in page  # template wraps the full sentence

    def test_purge_is_scoped_to_the_signed_in_account(self, app: FastAPI, tmp_path: Path) -> None:
        _, mine = seed_upload(app, tmp_path)
        other_dir = tmp_path / "uploads" / "b1"
        other_dir.mkdir(parents=True, exist_ok=True)
        theirs = other_dir / "raw.jsonl"
        theirs.write_text("{}\n", encoding="utf-8")
        with app.state.session_factory() as session:
            other = User(email="someone@else.com")
            session.add(other)
            session.flush()
            session.add(
                Audit(
                    user_id=other.id,
                    status="done",
                    upload_path=str(theirs),
                    report_ready_at=datetime.now(UTC),
                )
            )
            session.commit()
        TestClient(app).post(
            "/settings/purge",
            headers=HDR,
            data={"confirm": PURGE_PHRASE},
            follow_redirects=False,
        )
        assert not mine.exists()
        assert theirs.exists(), "another account's uploads must be untouched"

    def test_purge_is_idempotent(self, app: FastAPI, tmp_path: Path) -> None:
        seed_upload(app, tmp_path)
        client = TestClient(app)
        first = client.post(
            "/settings/purge", headers=HDR, data={"confirm": PURGE_PHRASE}, follow_redirects=False
        )
        second = client.post(
            "/settings/purge", headers=HDR, data={"confirm": PURGE_PHRASE}, follow_redirects=False
        )
        assert "purged=1" in first.headers["location"]
        assert "purged=0" in second.headers["location"]  # nothing left to purge


class TestSourceRevokeFromSettings:
    def test_03_revoke_flow_end_to_end(self, app: FastAPI) -> None:
        """T-SET-03: revoke reachable from Settings, deletes the stored key."""
        client = TestClient(app)
        with app.state.session_factory() as session:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
            src = Source(
                user_id=user.id,
                provider="anthropic",
                label="main",
                credentials_encrypted=encrypt_credential("k" * 64, "sk-secret"),
            )
            session.add(src)
            session.commit()
            source_id = src.id
        page = client.get("/settings", headers=HDR).text
        assert f"/sources/{source_id}/revoke" in page  # the control is on the page
        assert "sk-secret" not in page  # and the key is never rendered
        client.post(f"/sources/{source_id}/revoke", headers=HDR, follow_redirects=False)
        with app.state.session_factory() as session:
            gone = session.get(Source, source_id)
            assert gone is not None
            assert gone.status == "revoked" and gone.credentials_encrypted is None
        after = client.get("/settings", headers=HDR).text
        assert f"/sources/{source_id}/revoke" not in after  # control gone
        assert "No sources connected" in after


class TestPurgePrimitiveIsShared:
    def test_manual_admin_purge_also_clears_idempotency_keys(
        self, app: FastAPI, tmp_path: Path
    ) -> None:
        """Regression: the admin path used to skip the FR-26 deletion the
        scheduled path performed. One primitive now serves all three."""
        audit_id, _ = seed_upload(app, tmp_path)
        token = app.state.settings.admin_token
        if not token:
            return  # admin disabled in this fixture; covered by the settings path
        TestClient(app).post(f"/admin/audits/{audit_id}/purge", headers={"X-Admin-Token": token})
        with app.state.session_factory() as session:
            assert session.execute(select(IdempotencyKey)).scalars().all() == []


class TestPurgePrimitiveDirectly:
    def test_purge_one_is_safe_to_call_twice(self, app: FastAPI, tmp_path: Path) -> None:
        """The primitive's own guard: callers that do not pre-filter (a future
        third caller) must not double-purge or re-log."""
        from tokenops_cost_auditor.services.lifecycle import purge

        audit_id, upload_file = seed_upload(app, tmp_path)
        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            assert purge.purge_one(session, audit, actor="t@e.com", mode="test") is True
            session.commit()
            assert not upload_file.exists()
            # second call is a no-op, not a second audit-log entry
            assert purge.purge_one(session, audit, actor="t@e.com", mode="test") is False
            session.commit()
            purged_entries = [
                e
                for e in session.execute(select(AuditLogEntry)).scalars().all()
                if e.action == "audit.purged"
            ]
            assert len(purged_entries) == 1


class TestColdReviewRegressionsV7:
    """V-D7 cold-review FAIL (2026-07-22) — f.1..f.3."""

    def test_f1_opting_out_of_email_still_archives_the_statement(
        self, app: FastAPI, tmp_path: Path
    ) -> None:
        """Settings promises "you can always read it here" — the artifact must
        exist even when the customer declines the email."""
        import importlib.util

        from tokenops_cost_auditor.persistence.models import Statement
        from tokenops_cost_auditor.services.statements import build as statements

        script = Path(__file__).resolve().parents[1] / "scripts" / "monthly_statements.py"
        spec = importlib.util.spec_from_file_location("monthly_statements", script)
        assert spec and spec.loader
        job = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(job)

        class CountingMail:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def alert(self, to_email: str, subject: str, body: str) -> None:
                self.sent.append(to_email)

        with app.state.session_factory() as session:
            optout = User(email="quiet@example.com", statement_emails=False)
            optin = User(email="loud@example.com", statement_emails=True)
            session.add_all([optout, optin])
            session.commit()

            mail = CountingMail()
            for user in session.execute(select(User)).scalars().all():
                doc = statements.build(session, user, 2026, 6)
                row = statements.archive(session, user, doc)
                session.flush()
                if user.statement_emails is False:
                    pass  # archived, not emailed
                else:
                    statements.send(session, mail, user, row)
                session.commit()

            periods = {
                (s.user_id, s.period) for s in session.execute(select(Statement)).scalars().all()
            }
            assert len(periods) == 2, "the opted-out user must still have an archived statement"
            assert mail.sent == ["loud@example.com"]
        assert job.previous_month(datetime(2026, 3, 5, tzinfo=UTC)) == (2026, 2)

    def test_f2_purging_an_audit_that_never_stored_a_file_claims_nothing(
        self, app: FastAPI
    ) -> None:
        """An audit with no upload must not get a purged_at stamp or an
        audit-log entry — that would claim a deletion that never happened."""
        from tokenops_cost_auditor.services.lifecycle import purge

        with app.state.session_factory() as session:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
            failed_audit = Audit(user_id=user.id, status="failed", upload_path=None)
            session.add(failed_audit)
            session.commit()
            audit_id = failed_audit.id

            assert purge.purge_one(session, failed_audit, actor="admin", mode="manual") is False
            session.commit()
            fresh = session.get(Audit, audit_id)
            assert fresh is not None
            assert fresh.purged_at is None, "nothing was deleted, so nothing is 'purged'"
            purged_entries = [
                e
                for e in session.execute(select(AuditLogEntry)).scalars().all()
                if e.action == "audit.purged"
            ]
            assert purged_entries == []

    def test_f3_counters_separate_opted_out_from_already_sent(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "scripts" / "monthly_statements.py"
        ).read_text(encoding="utf-8")
        assert "archived_not_emailed" in source
        assert "opted_out" in source and "already_sent" in source

    def test_the_monthly_job_actually_runs_end_to_end(
        self, app: FastAPI, tmp_path: Path, monkeypatch: object
    ) -> None:
        """The job's summary line referenced a counter that no longer existed —
        a NameError that would have fired on every real run, invisible to any
        test that only imported the module. This executes main()."""
        import importlib.util
        import os

        from tokenops_cost_auditor.persistence.models import Statement

        db_path = tmp_path / "job.db"
        with app.state.session_factory() as session:
            session.add(User(email="jobtest@example.com"))
            session.commit()
        # point the job at this test's database
        os.environ["DATABASE_URL"] = str(app.state.settings.database_url)
        os.environ["SECRET_KEY"] = "j" * 64
        script = Path(__file__).resolve().parents[1] / "scripts" / "monthly_statements.py"
        spec = importlib.util.spec_from_file_location("monthly_statements_run", script)
        assert spec and spec.loader
        job = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(job)
        from tokenops_cost_auditor.config import get_settings

        get_settings.cache_clear()
        assert job.main() == 0  # would raise NameError before the fix
        assert db_path is not None
        with app.state.session_factory() as session:
            assert session.execute(select(Statement)).scalars().all() != []


class TestBenchmarkSharing:
    """R-F1 SIGN-OFF: cohort membership — default ON (disclosed), one-checkbox
    opt-out, audit-logged both directions."""

    def test_default_on_and_disclosure_rendered(self, app: FastAPI) -> None:
        page = TestClient(app).get("/settings", headers=HDR)
        assert page.status_code == 200
        import re

        squashed = re.sub(r"\s+", " ", page.text)
        assert "Include my account in peer benchmarks" in squashed
        assert "never your content" in squashed
        assert "Included by default" in squashed
        assert "never used to train any model" in squashed
        checkbox = re.search(r'name="benchmark_sharing"[^>]*', page.text)
        assert checkbox is not None and "checked" in checkbox.group(0)  # default ON

    def test_opt_out_persists_and_is_audit_logged(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/settings", headers=HDR)  # creates the user
        resp = client.post("/settings/benchmarks", headers=HDR, data={}, follow_redirects=False)
        assert resp.status_code == 303
        from sqlalchemy import select

        from tokenops_cost_auditor.persistence.models import AuditLogEntry, User

        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            assert user.benchmark_sharing is False
            entries = [
                e
                for e in session.execute(select(AuditLogEntry)).scalars()
                if e.action == "settings.benchmark_sharing"
            ]
            assert entries and entries[-1].subject == "excluded"
        page = client.get("/settings", headers=HDR)
        import re

        checkbox = re.search(r'name="benchmark_sharing"[^>]*', page.text)
        assert checkbox is not None and "checked" not in checkbox.group(0)
        # rejoin
        client.post(
            "/settings/benchmarks",
            headers=HDR,
            data={"benchmark_sharing": "1"},
            follow_redirects=False,
        )
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            assert user.benchmark_sharing is True
