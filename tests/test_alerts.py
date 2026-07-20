"""T-ALR-01..05 + T-FB-03 (PLAN-V15 V-D5 / WP-3b).

Alerts are OBSERVE-ONLY: X-02 forbids enforcement, and T-ALR-05 asserts it
against the package rather than trusting review.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    AlertEvent,
    AlertRule,
    Audit,
    Base,
    FindingRow,
    User,
)
from tokenops_cost_auditor.services.alerts import dispatch
from tokenops_cost_auditor.services.alerts.rules import (
    NEW_HIGH,
    SOFT_BUDGET,
    SPEND_SPIKE,
    WASTE_ABOVE,
    evaluate,
)

T0 = datetime(2026, 7, 1, tzinfo=UTC)
EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}


class CapturingMail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def alert(self, to_email: str, subject: str, body: str) -> None:
        self.sent.append((to_email, subject, body))


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(secret_key="k" * 64, database_url=f"sqlite:///{tmp_path}/al.db", _env_file=None)


@pytest.fixture()
def session(settings: Settings) -> Session:
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return Session(engine)


def make_user(session: Session) -> User:
    user = User(email=EMAIL)
    session.add(user)
    session.flush()
    return user


def add_audit(
    session: Session, uid: str, when: datetime, spend: float, waste: float = 0.0, days: int = 30
) -> Audit:
    a = Audit(
        user_id=uid,
        status="done",
        created_at=when,
        report_ready_at=when,
        observed_days=days,
        row_count=1000,
        total_spend_usd=spend,
        savings_pct=waste,
    )
    session.add(a)
    session.flush()
    return a


def arm(session: Session, uid: str, rule: str, threshold: float | None = None) -> None:
    session.add(AlertRule(user_id=uid, rule=rule, threshold=threshold, enabled=True))


class TestRules:
    def test_01_spend_spike(self, session: Session, settings: Settings) -> None:
        user = make_user(session)
        arm(session, user.id, SPEND_SPIKE, 30.0)
        add_audit(session, user.id, T0, spend=1000.0)
        add_audit(session, user.id, T0 + timedelta(days=7), spend=1400.0)  # +40%
        session.commit()
        firings = evaluate(session, settings, user)
        assert [f.rule for f in firings] == [SPEND_SPIKE]
        assert "$1,400.00/mo" in firings[0].subject and "40%" in firings[0].subject

    def test_01b_spend_spike_below_threshold_is_silent(
        self, session: Session, settings: Settings
    ) -> None:
        user = make_user(session)
        arm(session, user.id, SPEND_SPIKE, 30.0)
        add_audit(session, user.id, T0, spend=1000.0)
        add_audit(session, user.id, T0 + timedelta(days=7), spend=1290.0)  # +29%
        session.commit()
        assert evaluate(session, settings, user) == []

    def test_02_waste_above_target(self, session: Session, settings: Settings) -> None:
        user = make_user(session)
        arm(session, user.id, WASTE_ABOVE, 25.0)
        add_audit(session, user.id, T0, spend=900.0, waste=31.5)
        session.commit()
        firings = evaluate(session, settings, user)
        assert [f.rule for f in firings] == [WASTE_ABOVE]
        assert "31.5%" in firings[0].subject
        # exactly at target is not above it
        session.execute(select(Audit)).scalars().one().savings_pct = 25.0
        session.commit()
        assert evaluate(session, settings, user) == []

    def test_03_new_high_finding_only_when_new(self, session: Session, settings: Settings) -> None:
        user = make_user(session)
        arm(session, user.id, NEW_HIGH)
        a1 = add_audit(session, user.id, T0, spend=900.0)
        session.add(
            FindingRow(
                audit_id=a1.id,
                finding_id="D2-001",
                detector="d2_missing_cache",
                route="m1",
                severity="high",
                monthly_impact_usd=800.0,
                confidence="estimated",
                fix_text="x",
                evidence_sample=[],
            )
        )
        a2 = add_audit(session, user.id, T0 + timedelta(days=7), spend=900.0)
        # same route recurring: NOT new
        session.add(
            FindingRow(
                audit_id=a2.id,
                finding_id="D2-009",
                detector="d2_missing_cache",
                route="m1",
                severity="high",
                monthly_impact_usd=800.0,
                confidence="estimated",
                fix_text="x",
                evidence_sample=[],
            )
        )
        session.commit()
        assert evaluate(session, settings, user) == []
        # a genuinely new high-impact route fires
        session.add(
            FindingRow(
                audit_id=a2.id,
                finding_id="D1-002",
                detector="d1_oversized_model",
                route="m2",
                severity="high",
                monthly_impact_usd=1234.50,
                confidence="estimated",
                fix_text="x",
                evidence_sample=[],
            )
        )
        session.commit()
        firings = evaluate(session, settings, user)
        assert [f.rule for f in firings] == [NEW_HIGH]
        assert "$1,234.50/mo" in firings[0].subject

    def test_04_soft_budget_states_nothing_was_paused(
        self, session: Session, settings: Settings
    ) -> None:
        user = make_user(session)
        arm(session, user.id, SOFT_BUDGET, 500.0)
        add_audit(session, user.id, T0, spend=900.0)
        session.commit()
        firings = evaluate(session, settings, user)
        assert [f.rule for f in firings] == [SOFT_BUDGET]
        assert "nothing has been paused or limited" in firings[0].body

    def test_disabled_rules_never_fire(self, session: Session, settings: Settings) -> None:
        user = make_user(session)
        session.add(AlertRule(user_id=user.id, rule=WASTE_ABOVE, threshold=1.0, enabled=False))
        add_audit(session, user.id, T0, spend=900.0, waste=99.0)
        session.commit()
        assert evaluate(session, settings, user) == []


class TestDispatch:
    def test_sends_once_per_audit(self, session: Session, settings: Settings) -> None:
        user = make_user(session)
        arm(session, user.id, WASTE_ABOVE, 25.0)
        add_audit(session, user.id, T0, spend=900.0, waste=40.0)
        session.commit()
        mail = CapturingMail()
        assert len(dispatch.run_for_user(session, settings, mail, user)) == 1
        session.commit()
        assert len(mail.sent) == 1 and mail.sent[0][0] == EMAIL
        # a second tick on the same audit must not re-send
        assert dispatch.run_for_user(session, settings, mail, user) == []
        assert len(mail.sent) == 1
        assert len(session.execute(select(AlertEvent)).scalars().all()) == 1


class TestObserveOnly:
    def test_05_no_enforcement_path_exists(self) -> None:
        """X-02: alerting may notify. It may not act."""
        pkg = Path("src/tokenops_cost_auditor/services/alerts")
        banned = re.compile(
            r"\b(throttle|suspend|block_|disable_source|revoke|rate_limit|"
            r"cancel_subscription)\b|\.status\s*=(?!=)"
        )
        for path in pkg.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            # Strip docstrings: prose that NAMES the forbidden verbs (as this
            # package's own docs do) is not an enforcement path.
            for node in ast.walk(tree):
                if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef) and (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    node.body = node.body[1:] or [ast.Pass()]
            code = ast.unparse(ast.fix_missing_locations(tree))
            assert not banned.search(code), f"enforcement-shaped code in {path}"

    def test_alert_body_never_promises_enforcement(
        self, session: Session, settings: Settings
    ) -> None:
        user = make_user(session)
        for rule, threshold in ((SPEND_SPIKE, 1.0), (WASTE_ABOVE, 1.0), (SOFT_BUDGET, 1.0)):
            arm(session, user.id, rule, threshold)
        add_audit(session, user.id, T0, spend=100.0, waste=50.0)
        add_audit(session, user.id, T0 + timedelta(days=7), spend=900.0, waste=50.0)
        session.commit()
        for f in evaluate(session, settings, user):
            lowered = f.body.lower()
            for promise in ("we paused", "we blocked", "we capped", "we stopped", "we limited"):
                assert promise not in lowered


class TestAlertsPage:
    def test_settings_round_trip(self, app: FastAPI) -> None:
        client = TestClient(app)
        page = client.get("/alerts", headers=HDR)
        assert page.status_code == 200
        assert "never pause an audit" in page.text
        saved = client.post(
            "/alerts",
            headers=HDR,
            data={
                "waste_above_target_enabled": "1",
                "waste_above_target_threshold": "18",
                "soft_budget_enabled": "1",
                "soft_budget_threshold": "2500",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        with app.state.session_factory() as session:
            rules = {r.rule: r for r in session.execute(select(AlertRule)).scalars().all()}
            assert (
                rules["waste_above_target"].enabled
                and rules["waste_above_target"].threshold == 18.0
            )
            assert rules["soft_budget"].threshold == 2500.0
            assert rules["spend_spike_dod"].enabled is False  # unchecked box = off
        after = client.get("/alerts", headers=HDR).text
        assert 'value="18.0"' in after or 'value="18"' in after

    def test_prevent_stage_goes_live_once_rules_are_armed(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert "Not set up" in client.get("/dashboard", headers=HDR).text
        client.post(
            "/alerts",
            headers=HDR,
            data={"waste_above_target_enabled": "1", "waste_above_target_threshold": "20"},
            follow_redirects=False,
        )
        page = client.get("/dashboard", headers=HDR).text
        assert "1 armed" in page and "rule(s) armed" in page

    def test_unparseable_threshold_falls_back(self, app: FastAPI) -> None:
        client = TestClient(app)
        r = client.post(
            "/alerts",
            headers=HDR,
            data={
                "waste_above_target_enabled": "1",
                "waste_above_target_threshold": "not-a-number",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        with app.state.session_factory() as session:
            row = session.execute(
                select(AlertRule).where(AlertRule.rule == "waste_above_target")
            ).scalar_one()
            assert row.threshold is None and row.enabled is True
