"""T-STMT-01..03 (PLAN-V15 V-D6 / WP-4) — the Savings Statement.

The statement inherits R-Q9 law wholesale (founder 2026-07-22): verified
figures only in the headline, customer-reported and identified in their own
labelled sections, provenance stamps, and the FR-30 equiv-spend line where
billing plan is unknown. These are tests of that law, not of prose.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    Audit,
    Base,
    CallAggregate,
    FindingFeedback,
    FindingRow,
    Statement,
    User,
)
from tokenops_cost_auditor.services.report.model import EQUIV_SPEND_LINE
from tokenops_cost_auditor.services.statements import build as statements

JUNE = datetime(2026, 6, 1, tzinfo=UTC)
EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}


class CapturingMail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def alert(self, to_email: str, subject: str, body: str) -> None:
        self.sent.append((to_email, subject, body))


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path}/st.db")
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_month(session: Session, *, equiv: bool = False) -> User:
    """June: a finding applied, then re-audited cheaper — a verified saving,
    plus an untouched finding and a customer-reported figure."""
    user = User(email=EMAIL)
    session.add(user)
    session.flush()
    a1 = Audit(
        user_id=user.id,
        status="done",
        created_at=JUNE,
        report_ready_at=JUNE,
        observed_days=30,
        row_count=5000,
        total_spend_usd=900.0,
        savings_pct=30.0,
        equiv_spend=equiv,
    )
    session.add(a1)
    session.flush()
    session.add(
        FindingRow(
            audit_id=a1.id,
            finding_id="D2-001",
            detector="d2_missing_cache",
            route="m1",
            severity="high",
            monthly_impact_usd=1000.0,
            confidence="estimated",
            fix_text="x",
            evidence_sample=[],
        )
    )
    session.add(
        FindingFeedback(
            audit_id=a1.id,
            finding_id="D2-001",
            verdict="applied",
            actor=EMAIL,
            ts=JUNE + timedelta(hours=1),
        )
    )
    a2 = Audit(
        user_id=user.id,
        status="done",
        created_at=JUNE + timedelta(days=14),
        report_ready_at=JUNE + timedelta(days=14),
        observed_days=30,
        row_count=5200,
        total_spend_usd=600.0,
        savings_pct=12.0,
        equiv_spend=equiv,
    )
    session.add(a2)
    session.flush()
    session.add(
        FindingRow(
            audit_id=a2.id,
            finding_id="D2-009",
            detector="d2_missing_cache",
            route="m1",
            severity="med",
            monthly_impact_usd=250.0,
            confidence="estimated",
            fix_text="x",
            evidence_sample=[],
        )
    )
    session.add(
        FindingRow(
            audit_id=a2.id,
            finding_id="D1-001",
            detector="d1_oversized_model",
            route="m2",
            severity="med",
            monthly_impact_usd=300.0,
            confidence="estimated",
            fix_text="x",
            evidence_sample=[],
        )
    )
    session.add(
        FindingFeedback(
            audit_id=a2.id,
            finding_id="D1-001",
            verdict="dismissed",
            savings_realized_usd=75.0,
            actor=EMAIL,
            ts=JUNE + timedelta(days=15),
        )
    )
    session.commit()
    return user


class TestStatementArithmetic:
    def test_01_figures_match_hand_derivation(self, session: Session) -> None:
        """T-STMT-01. Hand derivation (all June):
        verified  = baseline 1000.00 - recomputed 250.00 = 750.00 (capped at
                    baseline; proved by the 14 Jun audit, 30 days >= 7)
        identified= 300.00 (D1-001, dismissed -> never applied, still open)
                    D2-009 excluded: its route is settled (R3)
        reported  = 75.00 (customer's own figure, separate line)
        spend     = 600.00 * 30/30 at the latest June audit
        """
        user = seed_month(session)
        doc = statements.build(session, user, 2026, 6)
        assert doc.verified_usd == 750.00
        assert doc.identified_usd == 300.00
        assert doc.customer_reported_usd == 75.00
        assert doc.spend_usd == 600.00
        assert doc.fixes_applied == 1

    def test_month_scoping_excludes_other_months(self, session: Session) -> None:
        user = seed_month(session)
        july = statements.build(session, user, 2026, 7)
        assert july.verified_usd == 0.0  # proved in June, credited to June
        assert july.customer_reported_usd == 0.0
        assert july.identified_usd == 0.0


class TestStatementLabelling:
    def test_02_verified_headline_never_absorbs_the_other_figures(self, session: Session) -> None:
        """T-STMT-02: R-Q9 labelling law, in the artifact itself."""
        user = seed_month(session)
        doc = statements.build(session, user, 2026, 6)
        assert "VERIFIED SAVINGS THIS MONTH: $750.00" in doc.body
        assert doc.subject.startswith("$750.00 verified savings")
        # identified sits in its own section, explicitly not savings
        assert "STILL ON THE TABLE (ESTIMATES, NOT SAVINGS)" in doc.body
        assert "$300.00 per month identified" in doc.body
        # customer-reported sits in its own section, explicitly not ours
        assert "REPORTED BY YOU (NOT OUR MEASUREMENT)" in doc.body
        assert "$75.00" in doc.body
        assert "never add them to" in doc.body
        # the three figures are never summed anywhere
        assert "1,125" not in doc.body and "$1,125.00" not in doc.body

    def test_provenance_stamps_every_audit(self, session: Session) -> None:
        user = seed_month(session)
        doc = statements.build(session, user, 2026, 6)
        assert "WHERE THESE NUMBERS COME FROM" in doc.body
        audits = session.execute(select(Audit)).scalars().all()
        for a in audits:
            assert f"{a.id[:4]}…{a.id[-3:]}" in doc.body

    def test_equiv_spend_line_appears_verbatim_when_billing_unknown(self, session: Session) -> None:
        """FR-30 carried into the statement, exactly as ruled."""
        user = seed_month(session, equiv=True)
        doc = statements.build(session, user, 2026, 6)
        assert doc.equiv_spend is True
        assert EQUIV_SPEND_LINE in doc.body

    def test_no_equiv_line_when_billing_is_metered(self, session: Session) -> None:
        user = seed_month(session, equiv=False)
        doc = statements.build(session, user, 2026, 6)
        assert EQUIV_SPEND_LINE not in doc.body

    def test_zero_state_states_nothing_rather_than_inventing(self, session: Session) -> None:
        user = User(email="quiet@example.com")
        session.add(user)
        session.commit()
        doc = statements.build(session, user, 2026, 6)
        assert doc.verified_usd == 0.0
        assert "VERIFIED SAVINGS THIS MONTH: none yet" in doc.body
        assert "No audit ran this month" in doc.body
        assert "$0.00 verified" not in doc.subject


class TestArchiveAndResend:
    def test_03_archive_is_idempotent_and_sent_artifacts_are_frozen(self, session: Session) -> None:
        """T-STMT-03: one row per user per month; a SENT statement is never
        rewritten, because it has already left the building."""
        user = seed_month(session)
        doc = statements.build(session, user, 2026, 6)
        row = statements.archive(session, user, doc)
        session.commit()
        # re-running the build refreshes the draft in place, never duplicates
        statements.archive(session, user, statements.build(session, user, 2026, 6))
        session.commit()
        assert len(session.execute(select(Statement)).scalars().all()) == 1

        mail = CapturingMail()
        assert statements.send(session, mail, user, row) is True
        session.commit()
        assert len(mail.sent) == 1
        assert mail.sent[0][1].startswith("$750.00 verified savings")
        # a second send is refused: at-most-once, same as alerts
        assert statements.send(session, mail, user, row) is False
        assert len(mail.sent) == 1

        # and the archived body is now frozen even if the figures move
        session.add(
            CallAggregate(
                audit_id=session.execute(select(Audit)).scalars().first().id,
                day=JUNE.date(),
                model="m9",
                calls=1,
                prompt_tokens=1,
                completion_tokens=1,
                cached_tokens=0,
                cost_usd=99999.0,
            )
        )
        session.commit()
        before = row.body_text
        statements.archive(session, user, statements.build(session, user, 2026, 6))
        session.commit()
        assert row.body_text == before


class TestStatementPages:
    def test_pages_render_and_resend(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert client.get("/statements").status_code == 401
        page = client.get("/statements", headers=HDR)
        assert page.status_code == 200
        assert "This month, so far" in page.text
        now = datetime.now(UTC)
        period = f"{now.year:04d}-{now.month:02d}"
        sent = client.post(f"/statements/{period}/send", headers=HDR, follow_redirects=False)
        assert sent.status_code == 303
        detail = client.get(f"/statements/{period}", headers=HDR)
        assert detail.status_code == 200 and "AI SPEND STATEMENT" in detail.text
        # resend delivers the archived artifact again without rewriting it
        again = client.post(f"/statements/{period}/send", headers=HDR, follow_redirects=False)
        assert again.status_code == 303
        with app.state.session_factory() as session:
            rows = session.execute(select(Statement)).scalars().all()
            assert len(rows) == 1 and rows[0].sent_at is not None
        assert client.get("/statements/1999-01", headers=HDR).status_code == 404

    def test_cross_user_statements_are_not_readable(self, app: FastAPI) -> None:
        client = TestClient(app)
        now = datetime.now(UTC)
        period = f"{now.year:04d}-{now.month:02d}"
        client.post(f"/statements/{period}/send", headers=HDR, follow_redirects=False)
        other = client.get(f"/statements/{period}", headers={"X-User-Email": "someone@else.com"})
        assert other.status_code == 404


class TestColdReviewRegressionsV6:
    """V-D6 cold-review FAIL (2026-07-22) — f.1..f.4."""

    def test_f1_pending_is_period_scoped_like_everything_else(self, session: Session) -> None:
        """A route applied in June must not be reported as pending in July's
        statement — the artifact would contradict itself."""
        user = User(email=EMAIL)
        session.add(user)
        session.flush()
        a = Audit(
            user_id=user.id,
            status="done",
            created_at=JUNE,
            report_ready_at=JUNE,
            observed_days=30,
            row_count=10,
            total_spend_usd=100.0,
        )
        session.add(a)
        session.flush()
        session.add(
            FindingRow(
                audit_id=a.id,
                finding_id="D2-001",
                detector="d2_missing_cache",
                route="m1",
                severity="high",
                monthly_impact_usd=500.0,
                confidence="estimated",
                fix_text="x",
                evidence_sample=[],
            )
        )
        session.add(
            FindingFeedback(
                audit_id=a.id,
                finding_id="D2-001",
                verdict="applied",
                actor=EMAIL,
                ts=JUNE + timedelta(hours=2),
            )
        )
        session.commit()
        june = statements.build(session, user, 2026, 6)
        july = statements.build(session, user, 2026, 7)
        assert "awaiting confirmation" in june.body  # applied in June
        assert "awaiting confirmation" not in july.body  # nothing to do with July

    def test_f2_an_audit_in_the_final_second_is_not_dropped(self, session: Session) -> None:
        """A 23:59:59 upper bound lost audits landing in the last second, so a
        statement could deny an audit whose figures it was already showing."""
        user = User(email=EMAIL)
        session.add(user)
        session.flush()
        edge = datetime(2026, 6, 30, 23, 59, 59, 800000, tzinfo=UTC)
        session.add(
            Audit(
                user_id=user.id,
                status="done",
                created_at=edge,
                report_ready_at=edge,
                observed_days=30,
                row_count=42,
                total_spend_usd=300.0,
                savings_pct=10.0,
            )
        )
        session.commit()
        doc = statements.build(session, user, 2026, 6)
        assert "No audit ran this month" not in doc.body
        assert "Audits this month: 1" in doc.body
        # and it does not leak into the next month
        assert "No audit ran this month" in statements.build(session, user, 2026, 7).body

    def test_f3_a_malformed_period_is_a_400_not_a_500(self, app: FastAPI) -> None:
        client = TestClient(app)
        for bad in ("abcd-ef", "2026-13", "2026-00", "99999-99", "2026"):
            r = client.post(f"/statements/{bad}/send", headers=HDR, follow_redirects=False)
            assert r.status_code == 400, bad

    def test_f4_one_bad_user_does_not_cost_the_others_their_statement(
        self, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        good = User(email="good@example.com")
        bad = User(email="bad@example.com")
        session.add_all([bad, good])  # bad is processed first
        session.commit()

        class OneBadRecipient:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def alert(self, to_email: str, subject: str, body: str) -> None:
                if to_email == "bad@example.com":
                    raise RuntimeError("mailbox rejected")
                self.sent.append(to_email)

        mail = OneBadRecipient()
        year, month = 2026, 6
        issued = failed = 0
        for user in session.execute(select(User)).scalars().all():
            try:
                doc = statements.build(session, user, year, month)
                row = statements.archive(session, user, doc)
                session.flush()
                if statements.send(session, mail, user, row):
                    issued += 1
                session.commit()
            except Exception:
                session.rollback()
                failed += 1
        assert (issued, failed) == (1, 1)
        assert mail.sent == ["good@example.com"]
        # January boundary in the monthly job's own helper
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "monthly_statements", "scripts/monthly_statements.py"
        )
        assert spec and spec.loader
        job = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(job)
        assert job.previous_month(datetime(2026, 1, 15, tzinfo=UTC)) == (2025, 12)
        assert job.previous_month(datetime(2026, 7, 1, tzinfo=UTC)) == (2026, 6)
