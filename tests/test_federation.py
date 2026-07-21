"""Signup federation — Google / Microsoft / GitHub (founder orders
2026-07-27 and 2026-07-21 "why only Google").

Config-gated end to end and PER PROVIDER: with no client id the button never
renders and the routes 404. Every callback grants the SAME signup credit as
the magic-link path (R-FREE-CONNECT one-meter law) via the shared
_record_login. Email trust is per provider: Google's email_verified claim,
Microsoft's presence-implies-verified claim, GitHub's verified flag on
/user/emails.
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


@pytest.fixture
def fedapp(tmp_path) -> Iterator[FastAPI]:
    """All three providers configured — the full-registry app."""
    settings = Settings(
        app_env="test",
        secret_key="test-secret",
        database_url=f"sqlite:///{tmp_path / 'f.db'}",
        upload_dir=tmp_path / "u",
        report_dir=tmp_path / "r",
        backup_dir=tmp_path / "b",
        google_client_id="g-id",
        google_client_secret="g-secret",
        microsoft_client_id="ms-id",
        microsoft_client_secret="ms-secret",
        github_client_id="gh-id",
        github_client_secret="gh-secret",
        _env_file=None,
    )
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


class _R:
    def __init__(self, payload: object) -> None:
        self._p = payload

    def json(self) -> object:
        return self._p


class TestConfigGating:
    @pytest.mark.parametrize("provider", ["google", "microsoft", "github"])
    def test_unconfigured_shows_no_button_and_404s(self, app: FastAPI, provider: str) -> None:
        client = TestClient(app)
        assert "Continue with" not in client.get("/login").text
        assert client.get(f"/auth/{provider}", follow_redirects=False).status_code == 404
        assert client.get(f"/auth/{provider}/callback", follow_redirects=False).status_code == 404

    def test_configured_shows_the_button_and_redirects(self, gapp: FastAPI) -> None:
        client = TestClient(gapp)
        page = client.get("/login").text
        assert "Continue with Google" in page
        start = client.get("/auth/google", follow_redirects=False)
        assert start.status_code == 303
        loc = start.headers["location"]
        assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=client-123" in loc and "state=" in loc

    def test_each_provider_gates_independently(self, gapp: FastAPI) -> None:
        """Google-only config: no Microsoft/GitHub buttons, and their routes
        404 — one provider's credentials never open another's door."""
        client = TestClient(gapp)
        page = client.get("/login").text
        assert "Continue with Google" in page
        assert "Continue with Microsoft" not in page
        assert "Continue with GitHub" not in page
        assert client.get("/auth/microsoft", follow_redirects=False).status_code == 404
        assert client.get("/auth/github", follow_redirects=False).status_code == 404

    def test_full_registry_renders_all_and_routes_each(self, fedapp: FastAPI) -> None:
        client = TestClient(fedapp)
        page = client.get("/login").text
        for label in ("Google", "Microsoft", "GitHub"):
            assert f"Continue with {label}" in page
        for provider, host in (
            ("google", "https://accounts.google.com/"),
            ("microsoft", "https://login.microsoftonline.com/"),
            ("github", "https://github.com/login/oauth/authorize"),
        ):
            start = client.get(f"/auth/{provider}", follow_redirects=False)
            assert start.status_code == 303
            assert start.headers["location"].startswith(host)

    def test_unknown_provider_is_404_even_fully_configured(self, fedapp: FastAPI) -> None:
        client = TestClient(fedapp)
        assert client.get("/auth/gitlab", follow_redirects=False).status_code == 404
        assert client.get("/auth/gitlab/callback", follow_redirects=False).status_code == 404


def _armed_state(application: FastAPI, client: TestClient) -> str:
    """Issue a signed state AND pin it to the client's cookie jar, the way
    federation_start does for a real browser — the callback requires both."""
    from tokenops_cost_auditor.web.auth import issue_magic_token

    token = issue_magic_token(application.state.settings.secret_key, "oauth-state")
    client.cookies.set("oauth_state", token)
    return token


class TestCallback:
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
            f"/auth/google/callback?code=c&state={_armed_state(gapp, client)}",
            follow_redirects=False,
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
            f"/auth/google/callback?code=c&state={_armed_state(gapp, client)}",
            follow_redirects=False,
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
            f"/auth/google/callback?code=c&state={_armed_state(gapp, client)}",
            follow_redirects=False,
        )
        assert resp.status_code == 400  # an unverified address must not claim an account

    def test_forged_state_is_refused(self, gapp: FastAPI) -> None:
        resp = TestClient(gapp).get(
            "/auth/google/callback?code=c&state=forged", follow_redirects=False
        )
        assert resp.status_code == 400

    def test_valid_signature_without_the_cookie_is_refused(self, gapp: FastAPI) -> None:
        """Cold-review f.1: a validly-SIGNED state from an attacker's own flow
        must still fail — the state is pinned to the browser that started it."""
        from tokenops_cost_auditor.web.auth import issue_magic_token

        token = issue_magic_token(gapp.state.settings.secret_key, "oauth-state")
        resp = TestClient(gapp).get(
            f"/auth/google/callback?code=c&state={token}", follow_redirects=False
        )
        assert resp.status_code == 400

    def test_client_id_without_secret_stays_dark(self, tmp_path) -> None:
        """Cold-review f.3: half a credential pair renders a button whose
        callback can never complete — so it renders nothing and 404s."""
        settings = Settings(
            app_env="test",
            secret_key="test-secret",
            database_url=f"sqlite:///{tmp_path / 'h.db'}",
            upload_dir=tmp_path / "u",
            report_dir=tmp_path / "r",
            backup_dir=tmp_path / "b",
            google_client_id="id-without-secret",
            _env_file=None,
        )
        application = create_app(settings)
        Base.metadata.create_all(application.state.engine)
        try:
            client = TestClient(application)
            assert "Continue with" not in client.get("/login").text
            assert client.get("/auth/google", follow_redirects=False).status_code == 404
        finally:
            application.state.engine.dispose()


class TestProviderEmailTrust:
    """Microsoft and GitHub land in the same shared login path — same session,
    same one-meter credit — but each with its own email-trust rule."""

    def _credits(self, application: FastAPI, email: str) -> int:
        with application.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == email)).scalar_one()
            return len(
                session.execute(select(Payment).where(Payment.user_id == user.id)).scalars().all()
            )

    def test_microsoft_email_claim_signs_in_with_one_credit(
        self, fedapp: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _R({"access_token": "at"}))
        # Entra userinfo: email claim, NO email_verified claim — presence is trust
        monkeypatch.setattr(httpx, "get", lambda *a, **k: _R({"email": "Entra@Corp.com"}))
        client = TestClient(fedapp, base_url="https://testserver")
        resp = client.get(
            f"/auth/microsoft/callback?code=c&state={_armed_state(fedapp, client)}",
            follow_redirects=False,
        )
        assert resp.status_code == 303 and resp.headers["location"] == "/dashboard"
        assert "top_session=" in resp.headers.get("set-cookie", "")
        assert self._credits(fedapp, "entra@corp.com") == 1

    def test_microsoft_missing_email_claim_is_refused(
        self, fedapp: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _R({"access_token": "at"}))
        monkeypatch.setattr(httpx, "get", lambda *a, **k: _R({"sub": "abc123"}))
        client = TestClient(fedapp)
        resp = client.get(
            f"/auth/microsoft/callback?code=c&state={_armed_state(fedapp, client)}",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_github_picks_the_primary_verified_address(
        self, fedapp: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        posted: dict = {}

        def post(*a, **k):
            posted.update(k)
            return _R({"access_token": "at"})

        monkeypatch.setattr(httpx, "post", post)
        monkeypatch.setattr(
            httpx,
            "get",
            lambda *a, **k: _R(
                [
                    {"email": "old@corp.com", "primary": False, "verified": True},
                    {"email": "Work@Corp.com", "primary": True, "verified": True},
                    {"email": "spoof@corp.com", "primary": False, "verified": False},
                ]
            ),
        )
        client = TestClient(fedapp, base_url="https://testserver")
        resp = client.get(
            f"/auth/github/callback?code=c&state={_armed_state(fedapp, client)}",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # GitHub's token endpoint answers urlencoded unless asked for JSON
        assert posted["headers"].get("Accept") == "application/json"
        assert self._credits(fedapp, "work@corp.com") == 1

    def test_github_unverified_only_list_is_refused(
        self, fedapp: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import httpx

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _R({"access_token": "at"}))
        monkeypatch.setattr(
            httpx,
            "get",
            lambda *a, **k: _R([{"email": "spoof@corp.com", "primary": True, "verified": False}]),
        )
        client = TestClient(fedapp)
        resp = client.get(
            f"/auth/github/callback?code=c&state={_armed_state(fedapp, client)}",
            follow_redirects=False,
        )
        assert resp.status_code == 400
