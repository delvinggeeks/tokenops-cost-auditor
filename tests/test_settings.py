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
