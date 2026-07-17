"""D10 tests — T-LIF-01..03 (scheduled purge, FR-21) per docs/05 §3."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import select

from test_runner import seed_audit
from tokenops_cost_auditor.persistence.models import Audit, AuditLogEntry, CallAggregate
from tokenops_cost_auditor.services.lifecycle.purge import purge_due

WINDOW_DAYS = 7


def age_audit(app: FastAPI, audit_id: str, days: int) -> None:
    """Backdate report_ready_at so the audit falls inside/outside the window."""
    with app.state.session_factory() as session:
        audit = session.get(Audit, audit_id)
        assert audit is not None
        audit.report_ready_at = datetime.now(UTC) - timedelta(days=days)
        session.commit()


class TestTLIF01Selection:
    def test_only_due_audits_selected(self, app: FastAPI) -> None:
        due = seed_audit(app, "openai_small.jsonl", email="due@example.com")
        fresh = seed_audit(app, "openai_small.jsonl", email="fresh@example.com")
        app.state.runner.run(due)
        app.state.runner.run(fresh)
        age_audit(app, due, days=8)
        age_audit(app, fresh, days=6)

        with app.state.session_factory() as session:
            purged = purge_due(session, WINDOW_DAYS)
        assert purged == [due]

        with app.state.session_factory() as session:
            assert session.get(Audit, fresh).upload_path is not None  # type: ignore[union-attr]

    def test_failed_audit_falls_back_to_created_at(self, app: FastAPI) -> None:
        """FR-23 'nothing retained beyond 7 days' must hold when no report exists."""
        audit_id = seed_audit(app, "openai_small.jsonl", email="fail@example.com")
        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            audit.status = "failed"
            audit.created_at = datetime.now(UTC) - timedelta(days=8)
            session.commit()
        with app.state.session_factory() as session:
            assert purge_due(session, WINDOW_DAYS) == [audit_id]

    def test_already_purged_not_reselected(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl", email="twice@example.com")
        app.state.runner.run(audit_id)
        age_audit(app, audit_id, days=9)
        with app.state.session_factory() as session:
            assert purge_due(session, WINDOW_DAYS) == [audit_id]
        with app.state.session_factory() as session:
            assert purge_due(session, WINDOW_DAYS) == []  # idempotent re-run


class TestTLIF02FilesRemoved:
    def test_upload_dir_gone_reports_and_aggregates_kept(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl", email="files@example.com")
        app.state.runner.run(audit_id)
        age_audit(app, audit_id, days=8)
        upload_dir = Path(app.state.settings.upload_dir) / audit_id
        report_pdf = Path(app.state.settings.report_dir) / audit_id / "report.pdf"
        assert upload_dir.exists() and report_pdf.exists()

        with app.state.session_factory() as session:
            purge_due(session, WINDOW_DAYS)

        assert not upload_dir.exists()  # raw upload removed (FR-21)
        assert report_pdf.exists()  # deliverable retained
        with app.state.session_factory() as session:
            aggs = list(
                session.scalars(select(CallAggregate).where(CallAggregate.audit_id == audit_id))
            )
        assert aggs  # derived counts retained (FR-21/FR-22)


class TestTLIF03AuditTrail:
    def test_audit_log_entry_and_purged_at_set(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, "openai_small.jsonl", email="trail@example.com")
        app.state.runner.run(audit_id)
        age_audit(app, audit_id, days=8)
        with app.state.session_factory() as session:
            purge_due(session, WINDOW_DAYS)
        with app.state.session_factory() as session:
            audit = session.get(Audit, audit_id)
            assert audit is not None
            assert audit.purged_at is not None and audit.upload_path is None
            entries = [
                e
                for e in session.scalars(
                    select(AuditLogEntry).where(AuditLogEntry.subject == audit_id)
                )
                if e.action == "audit.purged"
            ]
        assert len(entries) == 1
        assert entries[0].actor == "system@purge"
        assert entries[0].detail == {"mode": "scheduled"}


class TestFR26KeysPurgeWithUploads:
    def test_idempotency_keys_deleted_when_audit_purges(self, app: FastAPI) -> None:
        """FR-26: 7-day key retention shares the upload lifecycle (T-API-05)."""
        from tokenops_cost_auditor.persistence.models import IdempotencyKey, User

        audit_id = seed_audit(app, "openai_small.jsonl", email="keys@example.com")
        app.state.runner.run(audit_id)
        with app.state.session_factory() as session:
            user = session.scalar(select(User).where(User.email == "keys@example.com"))
            assert user is not None
            session.add(IdempotencyKey(user_id=user.id, key="idem-1", audit_id=audit_id))
            session.commit()
        age_audit(app, audit_id, days=8)
        with app.state.session_factory() as session:
            assert purge_due(session, WINDOW_DAYS) == [audit_id]
        with app.state.session_factory() as session:
            remaining = list(
                session.scalars(
                    select(IdempotencyKey).where(IdempotencyKey.audit_id == audit_id)
                )
            )
        assert remaining == []  # key gone with the upload
