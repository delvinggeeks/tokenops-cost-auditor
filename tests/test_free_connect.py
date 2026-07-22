"""R-FREE-CONNECT (founder-ratified 2026-07-27) — Free connects one source;
one free audit, either path, one meter.

The meter is the signup comp credit. Before this ruling the marketed free
audit was UNWIRED: no signup credit existed, so "Start free — 1 audit, no
card" 402'd at the payment gate. These tests walk the promise end to end.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Payment, Source, User

EMAIL = "freeconnect@example.com"
HDR = {"X-User-Email": EMAIL}


class _Recorder:
    def __init__(self) -> None:
        self.magic_links: list[tuple[str, str]] = []

    def magic_link(self, to_email: str, link_url: str) -> None:
        self.magic_links.append((to_email, link_url))

    def report_ready(self, to_email: str, report_url: str) -> None:
        pass


def fresh_signup(app: FastAPI, email: str = EMAIL) -> TestClient:
    recorder = _Recorder()
    app.state.mail = recorder
    client = TestClient(app, base_url="https://testserver")
    client.post("/auth/signin-link", data={"email": email})
    client.get(recorder.magic_links[-1][1], follow_redirects=False)
    return client


class TestTheSignupCredit:
    def test_first_login_grants_exactly_one_comp_credit(self, app: FastAPI) -> None:
        client = fresh_signup(app)
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            credits = (
                session.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            )
        assert len(credits) == 1
        assert credits[0].provider == "comp" and credits[0].amount == 0.0
        assert credits[0].audit_id is None  # unconsumed
        # a second login does NOT grant another
        recorder = _Recorder()
        app.state.mail = recorder
        client.post("/auth/signin-link", data={"email": EMAIL})
        client.get(recorder.magic_links[-1][1], follow_redirects=False)
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            n = len(
                session.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            )
        assert n == 1, "the meter never regenerates"

    def test_the_free_upload_promise_is_now_wired(self, app: FastAPI) -> None:
        """THE hole this ruling closed: a fresh signup's upload must not 402."""
        client = fresh_signup(app)
        resp = client.post(
            "/api/v1/audits",
            files={"file": ("calls.jsonl", b'{"ts": "2026-07-01T00:00:00Z"}\n')},
        )
        assert resp.status_code == 201, resp.text
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            credit = session.execute(select(Payment).where(Payment.user_id == user.id)).scalar_one()
        assert credit.audit_id is not None, "the upload consumed the one meter"
        # second upload: the meter is spent
        resp2 = client.post(
            "/api/v1/audits",
            files={"file": ("more.jsonl", b'{"ts": "2026-07-02T00:00:00Z"}\n')},
        )
        assert resp2.status_code == 402


class TestFreeConnectsOneSource:
    def test_free_plan_allows_one_connection(self, app: FastAPI) -> None:
        assert app.state.settings.plan_source_limits["free"] == 1
        client = TestClient(app)
        resp = client.post(
            "/sources",
            headers=HDR,
            data={"provider": "openai", "label": "prod", "api_key": "sk-x"},
            follow_redirects=False,
        )
        assert resp.status_code == 303  # connect succeeds on Free now
        # the SECOND connection hits the honest limit
        resp2 = client.post(
            "/sources",
            headers=HDR,
            data={"provider": "anthropic", "label": "prod2", "api_key": "sk-y"},
            follow_redirects=False,
        )
        assert resp2.status_code == 403

    def test_the_scheduler_never_pulls_free_sources(self, app: FastAPI) -> None:
        """The entitlement filter is now load-bearing (R-FREE-CONNECT §4):
        Free's one connection gets its one audit at connect time and is
        never scheduled — the COGS bound of the whole tier."""
        from tokenops_cost_auditor.services.connectors import schedule

        with app.state.session_factory() as session:
            user = User(email="freesched@example.com")
            session.add(user)
            session.flush()
            session.add(
                Source(
                    user_id=user.id,
                    provider="openai",
                    label="x",
                    credentials_encrypted=b"c",
                )
            )
            session.commit()
            from datetime import UTC, datetime

            due = schedule.due_pulls(session, datetime.now(UTC), app.state.settings)
        assert due == [], "a free source must never be due for a scheduled pull"
