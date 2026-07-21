"""Signup federation — Google OAuth (founder order 2026-07-27).

Config-gated end to end: with no client id the button never renders and the
routes 404. The callback grants the SAME signup credit as the magic-link
path (R-FREE-CONNECT one-meter law) via the shared _record_login.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.persistence.models import Base, Payment, User


@pytest.fixture
def gapp(tmp_path) -> Iterator[FastAPI]:
    settings = Settings(
        app_env="test",
        secret_key="test-secret",
        database_url=f"sqlite:///{tmp_path / 'g.db'}",
        upload_dir=tmp_path / "u",
        report_dir=tmp_path / "r",
        backup_dir=tmp_path / "b",
        google_client_id="client-123",
        google_client_secret="secret-456",
        _env_file=None,
    )
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


class TestConfigGating:
    def test_unconfigured_shows_no_button_and_404s(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert "Continue with Google" not in client.get("/login").text
        assert client.get("/auth/google", follow_redirects=False).status_code == 404
        assert client.get("/auth/google/callback", follow_redirects=False).status_code == 404

    def test_configured_shows_the_button_and_redirects(self, gapp: FastAPI) -> None:
        client = TestClient(gapp)
        page = client.get("/login").text
        assert "Continue with Google" in page
        start = client.get("/auth/google", follow_redirects=False)
        assert start.status_code == 303
        loc = start.headers["location"]
        assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=client-123" in loc and "state=" in loc


class TestCallback:
    def _state(self, gapp: FastAPI) -> str:
        from tokenops_cost_auditor.web.auth import issue_magic_token

        return issue_magic_token(gapp.state.settings.secret_key, "oauth-state")

    def test_verified_google_email_gets_session_and_one_credit(
        self, gapp: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        class R:
            def __init__(self, payload: dict) -> None:
                self._p = payload

            def json(self) -> dict:
                return self._p

        monkeypatch.setattr(httpx, "post", lambda *a, **k: R({"access_token": "at"}))
        monkeypatch.setattr(
            httpx,
            "get",
            lambda *a, **k: R({"email": "Fed@Corp.com", "email_verified": True}),
        )
        client = TestClient(gapp, base_url="https://testserver")
        resp = client.get(
            f"/auth/google/callback?code=c&state={self._state(gapp)}", follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/dashboard"
        assert "top_session=" in resp.headers.get("set-cookie", "")
        with gapp.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == "fed@corp.com")).scalar_one()
            credits = (
                session.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            )
        assert len(credits) == 1 and credits[0].provider == "comp"
        # second federation login: no second credit (one meter, ever)
        client.get(
            f"/auth/google/callback?code=c&state={self._state(gapp)}", follow_redirects=False
        )
        with gapp.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == "fed@corp.com")).scalar_one()
            n = len(
                session.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            )
        assert n == 1

    def test_unverified_email_is_refused(
        self, gapp: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        class R:
            def __init__(self, payload: dict) -> None:
                self._p = payload

            def json(self) -> dict:
                return self._p

        monkeypatch.setattr(httpx, "post", lambda *a, **k: R({"access_token": "at"}))
        monkeypatch.setattr(
            httpx,
            "get",
            lambda *a, **k: R({"email": "spoof@corp.com", "email_verified": False}),
        )
        client = TestClient(gapp)
        resp = client.get(
            f"/auth/google/callback?code=c&state={self._state(gapp)}", follow_redirects=False
        )
        assert resp.status_code == 400  # an unverified address must not claim an account

    def test_forged_state_is_refused(self, gapp: FastAPI) -> None:
        resp = TestClient(gapp).get(
            "/auth/google/callback?code=c&state=forged", follow_redirects=False
        )
        assert resp.status_code == 400
