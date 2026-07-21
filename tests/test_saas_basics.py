"""R-SAAS-BASICS (founder, 2026-07-26) — items 1-3 + 4a.

1: the plan sold as "Scale" everywhere public (the internal key stays "team":
subscription rows are data, migrations are additive-only). 2: support is
reachable with a stated response time. 3: status page linked. 4a: closing an
account is a first-class path that does everything the page promises.
"""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    Audit,
    AuditLogEntry,
    Source,
    Subscription,
    User,
)

EMAIL = "basics@example.com"
HDR = {"X-User-Email": EMAIL}
PLAN_NAME = re.compile(r"\bTeam\b")  # case-sensitive: "FinOps teams" stays legal


def grant_team(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan="team"))
        session.commit()


class TestTheScaleRename:
    def test_the_catalogue_sells_scale_not_team(self, app: FastAPI) -> None:
        from tokenops_cost_auditor.services.payments import plans

        plan = plans.get(app.state.settings, "team")
        assert plan.name == "Scale"
        assert "priority support" in plan.blurb
        assert plan.key == "team"  # data stays data — no migration for a rename

    def test_no_public_surface_says_team_as_a_plan_name(self, app: FastAPI) -> None:
        """The ruled test. Rendered pages, not source greps — str.title() on
        the internal key was one resurrection path already."""
        grant_team(app)
        client = TestClient(app)
        for path in ("/", "/legal/terms"):
            assert not PLAN_NAME.search(client.get(path).text), path
        for path in ("/billing", "/settings", "/dashboard", "/sources"):
            page = client.get(path, headers=HDR)
            assert page.status_code == 200, path
            assert not PLAN_NAME.search(page.text), f"{path} still says Team"
            assert "Scale" in page.text or path not in ("/billing", "/settings"), path

    def test_the_topbar_badge_uses_the_catalogue_name(self, app: FastAPI) -> None:
        grant_team(app)
        page = TestClient(app).get("/dashboard", headers=HDR)
        assert 'class="plan-badge">Scale</span>' in page.text


class TestSupportAndStatus:
    def test_support_is_reachable_from_app_footer_and_billing(self, app: FastAPI) -> None:
        client = TestClient(app)
        for path, where in (
            ("/dashboard", "app sidebar"),
            ("/", "public footer"),
            ("/billing", "billing page"),
        ):
            page = client.get(path, headers=HDR)
            assert "mailto:support@tokenops.cloud" in page.text, where
        # the response-time promise travels with the affordance
        assert "1 business day" in client.get("/billing", headers=HDR).text

    def test_status_page_is_linked_publicly(self, app: FastAPI) -> None:
        page = TestClient(app).get("/")
        assert 'href="https://status.tokenops.cloud"' in page.text


class TestCloseAccount:
    def _seed(self, app: FastAPI, tmp_path) -> None:
        grant_team(app)
        # per-audit directory, like the real upload route: purge_one deletes
        # the upload's PARENT dir, and a bare tmp_path file would take the
        # test database with it
        updir = tmp_path / "up-held"
        updir.mkdir()
        upload = updir / "held.jsonl"
        upload.write_text("{}")
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            session.add(
                Source(
                    user_id=user.id,
                    provider="openai",
                    label="prod",
                    credentials_encrypted=b"cipher",
                )
            )
            session.add(
                Audit(
                    user_id=user.id,
                    status="done",
                    upload_path=str(upload),
                    row_count=1,
                    observed_days=1,
                )
            )
            session.commit()

    def test_wrong_phrase_closes_nothing(self, app: FastAPI, tmp_path) -> None:
        self._seed(app, tmp_path)
        resp = TestClient(app).post(
            "/settings/close-account",
            headers=HDR,
            data={"confirm": "close my account"},
            follow_redirects=False,
        )
        assert resp.status_code == 303 and "closed=-1" in resp.headers["location"]
        with app.state.session_factory() as session:
            assert (
                session.execute(select(Source).where(Source.status == "active")).scalars().all()
            ), "wrong phrase must not revoke anything"

    def test_the_page_promises_are_all_kept(self, app: FastAPI, tmp_path) -> None:
        """Purge, key revocation with ciphertext deletion, local subscription
        cancel, session kill, audit log — everything the settings page states."""
        self._seed(app, tmp_path)
        resp = TestClient(app).post(
            "/settings/close-account",
            headers=HDR,
            data={"confirm": "CLOSE MY ACCOUNT"},
            follow_redirects=False,
        )
        assert resp.status_code == 303 and resp.headers["location"] == "/"
        set_cookie = resp.headers.get("set-cookie", "")
        assert "top_session=" in set_cookie and (
            'top_session=""' in set_cookie
            or "Max-Age=0" in set_cookie
            or "expires" in set_cookie.lower()
        ), "the session cookie must be cleared"
        with app.state.session_factory() as session:
            audit = session.execute(select(Audit)).scalars().one()
            assert audit.upload_path is None and audit.purged_at is not None
            source = session.execute(select(Source)).scalars().one()
            assert source.status == "revoked" and source.credentials_encrypted is None
            sub = session.execute(select(Subscription)).scalars().one()
            assert sub.status == "cancelled"
            entry = (
                session.execute(
                    select(AuditLogEntry).where(AuditLogEntry.action == "account.closed")
                )
                .scalars()
                .one()
            )
            assert (entry.detail or {}).get("provider_cancellation_required") is True

    def test_the_settings_page_states_the_consequences(self, app: FastAPI) -> None:
        page = TestClient(app).get("/settings", headers=HDR).text
        assert "CLOSE MY ACCOUNT" in page
        for consequence in (
            "revoked",
            "cancelled on our side",
            "signed out",
            "append-only audit log",
            "1 business day",
        ):
            assert consequence in page, f"consequence not stated: {consequence}"

    def test_the_digest_carries_the_provider_cancellation_task(
        self, app: FastAPI, tmp_path
    ) -> None:
        """The page promises provider closure within 1 business day; the daily
        digest line to the founder is what keeps that promise."""
        import importlib.util
        from pathlib import Path

        self._seed(app, tmp_path)
        TestClient(app).post(
            "/settings/close-account",
            headers=HDR,
            data={"confirm": "CLOSE MY ACCOUNT"},
            follow_redirects=False,
        )
        script = Path(__file__).resolve().parents[1] / "scripts" / "daily_digest.py"
        spec = importlib.util.spec_from_file_location("daily_digest", script)
        assert spec and spec.loader
        digest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(digest)
        with app.state.session_factory() as session:
            body = digest.build_digest(session, app.state.settings)
        assert "NEED provider-side subscription cancellation" in body
        assert EMAIL in body
