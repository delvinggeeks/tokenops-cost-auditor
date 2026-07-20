"""T-SAV-01..06 — R-Q9 verified-savings formula. MONEY MATH: exact-value
goldens, derivation in tests/fixtures/pricing_golden_NOTES.md."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    Audit,
    Base,
    FindingFeedback,
    FindingRow,
    User,
)
from tokenops_cost_auditor.services.dashboard.savings import compute

T0 = datetime(2026, 7, 1, tzinfo=UTC)


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path}/sav.db")
    Base.metadata.create_all(engine)
    return Session(engine)


def seed(session: Session) -> str:
    user = User(email="owner@example.com")
    session.add(user)
    session.flush()
    return user.id


def add_audit(session: Session, uid: str, when: datetime, days: int) -> Audit:
    a = Audit(
        user_id=uid,
        status="done",
        created_at=when,
        observed_days=days,
        row_count=1000,
        report_ready_at=when,
    )
    session.add(a)
    session.flush()
    return a


def add_finding(session: Session, audit_id: str, fid: str, det: str, usd: float) -> None:
    session.add(
        FindingRow(
            audit_id=audit_id,
            finding_id=fid,
            detector=det,
            severity="high",
            monthly_impact_usd=usd,
            confidence="estimated",
            fix_text="x",
            evidence_sample=[],
        )
    )


class TestVerifiedSavings:
    def test_01_applied_then_reaudited_is_verified(self, session: Session) -> None:
        uid = seed(session)
        a1 = add_audit(session, uid, T0, 30)
        add_finding(session, a1.id, "D2-001", "d2_missing_cache", 1000.0)
        session.add(
            FindingFeedback(
                audit_id=a1.id,
                finding_id="D2-001",
                verdict="applied",
                actor="owner@example.com",
                ts=T0 + timedelta(hours=1),
            )
        )
        # later audit covering 30 days: same route now costs 250 -> delta 750
        a2 = add_audit(session, uid, T0 + timedelta(days=10), 30)
        add_finding(session, a2.id, "D2-001", "d2_missing_cache", 250.0)
        session.commit()
        s = compute(session, uid)
        assert s.verified_usd == 750.00
        assert s.verified_count == 1 and s.pending_count == 0

    def test_02_pending_until_a_qualifying_audit_exists(self, session: Session) -> None:
        uid = seed(session)
        a1 = add_audit(session, uid, T0, 30)
        add_finding(session, a1.id, "D2-001", "d2_missing_cache", 1000.0)
        session.add(
            FindingFeedback(
                audit_id=a1.id,
                finding_id="D2-001",
                verdict="applied",
                actor="o@e.com",
                ts=T0 + timedelta(hours=1),
            )
        )
        session.commit()
        assert compute(session, uid).verified_usd == 0.0  # no later audit yet
        # a later audit covering only 3 days does NOT qualify (R-Q9 >= 7 days)
        a2 = add_audit(session, uid, T0 + timedelta(days=2), 3)
        add_finding(session, a2.id, "D2-001", "d2_missing_cache", 100.0)
        session.commit()
        s = compute(session, uid)
        assert s.verified_usd == 0.0 and s.pending_count == 1

    def test_03_capped_at_original_estimate_and_never_negative(self, session: Session) -> None:
        uid = seed(session)
        a1 = add_audit(session, uid, T0, 30)
        add_finding(session, a1.id, "D3-001", "d3_prompt_bloat", 500.0)
        session.add(
            FindingFeedback(
                audit_id=a1.id,
                finding_id="D3-001",
                verdict="applied",
                actor="o@e.com",
                ts=T0 + timedelta(hours=1),
            )
        )
        # regression: the route got WORSE (900 > 500) -> max(0, ...) = 0, never negative
        a2 = add_audit(session, uid, T0 + timedelta(days=10), 30)
        add_finding(session, a2.id, "D3-001", "d3_prompt_bloat", 900.0)
        session.commit()
        assert compute(session, uid).verified_usd == 0.0

    def test_04_customer_reported_never_in_headline(self, session: Session) -> None:
        uid = seed(session)
        a1 = add_audit(session, uid, T0, 30)
        add_finding(session, a1.id, "D1-001", "d1_oversized_model", 400.0)
        session.add(
            FindingFeedback(
                audit_id=a1.id,
                finding_id="D1-001",
                verdict="dismissed",
                savings_realized_usd=333.0,
                actor="o@e.com",
                ts=T0 + timedelta(hours=1),
            )
        )
        session.commit()
        s = compute(session, uid)
        assert s.customer_reported_usd == 333.00
        assert s.verified_usd == 0.0  # dismissed + self-reported never verifies

    def test_05_unapplied_are_identified_not_savings(self, session: Session) -> None:
        uid = seed(session)
        a1 = add_audit(session, uid, T0, 30)
        add_finding(session, a1.id, "D1-001", "d1_oversized_model", 400.0)
        add_finding(session, a1.id, "D2-001", "d2_missing_cache", 600.0)
        session.commit()
        s = compute(session, uid)
        assert s.identified_usd == 1000.00 and s.verified_usd == 0.0

    def test_06_no_audits_is_all_zero(self, session: Session) -> None:
        uid = seed(session)
        session.commit()
        s = compute(session, uid)
        assert (s.verified_usd, s.identified_usd, s.customer_reported_usd) == (0.0, 0.0, 0.0)
