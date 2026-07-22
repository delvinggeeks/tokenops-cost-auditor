"""Readiness audit (2026-07-22) — Wave 4: true END-TO-END tests.

The workflow audit found that connect and alerts had NO test exercising the
full path — units were covered, the seams were not, which is exactly how the
connect-wizard and other defects shipped green. These tests walk the whole
slice with the real pull, the real audit, the real scheduler tick, and the
real rendered surfaces — only the provider HTTP and mail are faked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    AlertEvent,
    Audit,
    FindingRow,
    Source,
    SourceUsage,
    Subscription,
    User,
)
from tokenops_cost_auditor.services.connectors import schedule
from tokenops_cost_auditor.services.connectors.crypto import encrypt_credential
from tokenops_cost_auditor.services.connectors.pull import run_pull
from tokenops_cost_auditor.services.connectors.source_audit import run_source_audit


def _usage_page(day: datetime) -> dict:
    """A real OpenAI usage page with waste planted (a frontier model doing
    tiny completions → oversized-model; heavy uncached repeats → missing
    cache) so the detectors have something to find."""
    return {
        "object": "page",
        "data": [
            {
                "object": "bucket",
                "start_time": int(day.timestamp()),
                "end_time": int((day + timedelta(days=1)).timestamp()),
                "results": [
                    {
                        "object": "organization.usage.completions.result",
                        "model": "gpt-5.6-sol",
                        "num_model_requests": 500,
                        "input_tokens": 4_000_000,
                        "input_cached_tokens": 0,
                        "output_tokens": 20_000,
                    },
                ],
            }
        ],
        "has_more": False,
        "next_page": None,
    }


class _FakeHTTP:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.status_code = 200

    def get(self, url: str, params: dict, headers: dict) -> _FakeHTTP:
        return self

    def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        return None


class CapturingMail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def alert(self, to, subject, body) -> None:
        self.sent.append((to, subject, body))

    def magic_link(self, *a) -> None:
        pass

    def report_ready(self, *a) -> None:
        pass


def _paid_source(app: FastAPI, email: str = "e2e@example.com") -> tuple[str, str]:
    email = email.lower()
    with app.state.session_factory() as session:
        user = User(email=email)
        session.add(user)
        session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan="pro", status="active"))
        src = Source(
            user_id=user.id,
            provider="openai",
            label="prod",
            credentials_encrypted=encrypt_credential(app.state.settings.secret_key, "sk-admin-x"),
        )
        session.add(src)
        session.commit()
        return user.id, src.id


class TestConnectEndToEnd:
    def test_connect_pull_audit_report_dashboard(self, app: FastAPI) -> None:
        """The whole connect slice: encrypted key → real pull persists usage →
        real audit produces findings + report.json → the dashboard shows the
        numbers. No stubbed kickoff, no empty FakeHTTP."""
        settings = app.state.settings
        _, source_id = _paid_source(app)
        page = _usage_page(datetime(2026, 7, 18, tzinfo=UTC))

        with app.state.session_factory() as session:
            src = session.get(Source, source_id)
            pull_stats = run_pull(session, settings, src, _FakeHTTP(page))
            session.commit()
            assert pull_stats.upserted > 0
            usage = session.execute(
                select(SourceUsage).where(SourceUsage.source_id == source_id)
            ).scalars().all()
            assert usage, "the pull must persist usage buckets"

            src = session.get(Source, source_id)
            run_source_audit(session, settings, app.state.pricing_table, src)
            session.commit()

            audit = session.execute(select(Audit)).scalars().one()
            assert audit.status == "done" and audit.report_ready_at is not None
            findings = session.execute(
                select(FindingRow).where(FindingRow.audit_id == audit.id)
            ).scalars().all()
            assert findings, "the planted waste must surface at least one finding"
            assert (settings.report_dir / audit.id / "report.json").exists()
            user_id = src.user_id
            user_email = session.get(User, user_id).email

        # the dashboard reflects the audit the pull produced — the full loop
        page_html = TestClient(app).get("/dashboard", headers={"X-User-Email": user_email}).text
        assert page_html.count("$") > 0  # money surfaces rendered

    def test_second_pull_is_idempotent(self, app: FastAPI) -> None:
        settings = app.state.settings
        _, source_id = _paid_source(app, "e2e2@example.com")
        page = _usage_page(datetime(2026, 7, 18, tzinfo=UTC))
        with app.state.session_factory() as session:
            src = session.get(Source, source_id)
            run_pull(session, settings, src, _FakeHTTP(page))
            session.commit()
            first = session.execute(
                select(SourceUsage).where(SourceUsage.source_id == source_id)
            ).scalars().all()
            src = session.get(Source, source_id)
            run_pull(session, settings, src, _FakeHTTP(page))
            session.commit()
            second = session.execute(
                select(SourceUsage).where(SourceUsage.source_id == source_id)
            ).scalars().all()
        assert len(first) == len(second), "a repeated pull upserts, never duplicates"


class TestAlertsEndToEnd:
    def test_config_to_tick_to_email_to_history(self, app: FastAPI) -> None:
        """The whole alerts slice: POST the budget rule → a real scheduler tick
        evaluates it against a real audit → an email is sent → the /alerts
        history page shows the fired event."""
        settings = app.state.settings
        email = "alertse2e@example.com"
        _, source_id = _paid_source(app, email)
        HDR = {"X-User-Email": email}
        client = TestClient(app)

        # 1. configure a low soft-budget so the audit's run-rate trips it
        resp = client.post(
            "/alerts",
            headers=HDR,
            data={"soft_budget_enabled": "1", "soft_budget_threshold": "1"},
            follow_redirects=False,
        )
        assert resp.status_code in (200, 303)

        # 2. give the account an audit with spend (pull → audit), then tick
        page = _usage_page(datetime.now(UTC) - timedelta(days=1))
        mail = CapturingMail()
        with app.state.session_factory() as session:
            src = session.get(Source, source_id)
            run_pull(session, settings, src, _FakeHTTP(page))
            session.commit()
            src = session.get(Source, source_id)
            src.last_pull_at = datetime.now(UTC)  # make the audit due
            run_source_audit(session, settings, app.state.pricing_table, src)
            session.commit()
            # 3. the real tick evaluates alerts and sends
            schedule.tick(session, settings, app.state.pricing_table, mail=mail)

        # 4. an alert email went out
        assert any("budget" in subj.lower() for _, subj, _ in mail.sent), mail.sent
        # 5. the history is recorded and rendered on /alerts
        with app.state.session_factory() as session:
            events = session.execute(select(AlertEvent)).scalars().all()
            assert events, "the fired alert must be recorded"
        history = client.get("/alerts", headers=HDR).text
        assert "budget" in history.lower()
