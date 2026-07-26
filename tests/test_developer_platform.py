"""S-6 tests (R-SDK-PLATFORM) — the READ platform, end to end.

Covers the three surfaces the founder scoped in one milestone:
- personal READ API tokens (rt_): mint → read → scope-enforced → revoke;
- the read endpoints (counts-only FR-22, tenant-isolated);
- the OAuth 2.0 authorization-code + PKCE server: register → authorize →
  token exchange → read, plus the adversarial cases (single-use codes, bad
  PKCE, wrong secret, exact redirect match, app-revoke kills tokens, CSRF/owner
  binding on the consent POST).
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    ApiToken,
    Audit,
    FindingRow,
    OAuthApp,
    Subscription,
    User,
)
from tokenops_cost_auditor.web import api_scopes

EMAIL = "dev-owner@example.com"
OTHER = "other-owner@example.com"
HDR = {"X-User-Email": EMAIL}
OTHER_HDR = {"X-User-Email": OTHER}


# ----------------------------------------------------------------- helpers


def grant(app: FastAPI, email: str = EMAIL, plan: str = "pro") -> str:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email)
            session.add(user)
            session.flush()
        session.add(Subscription(user_id=user.id, provider="stripe", plan=plan))
        session.commit()
        return user.id


def seed_audit(app: FastAPI, user_id: str, *, spend: float = 42.5) -> str:
    with app.state.session_factory() as session:
        audit = Audit(
            user_id=user_id,
            status="done",
            row_count=120,
            observed_days=7,
            total_spend_usd=spend,
            projected_spend_usd=spend * 4,
            savings_pct=18.0,
        )
        session.add(audit)
        session.flush()
        session.add(
            FindingRow(
                audit_id=audit.id,
                finding_id="d1-001",
                detector="d1_model_overkill",
                route="gpt-5.4",
                severity="high",
                monthly_impact_usd=31.0,
                confidence="ESTIMATED",
                fix_text="Route these calls to a cheaper model.",
                evidence_sample=[],
            )
        )
        session.commit()
        return audit.id


def mint_token(client: TestClient, scopes: list[str], label: str = "nb") -> str:
    # httpx form-encodes a dict with list values as repeated keys.
    resp = client.post(
        "/settings/developer/tokens",
        data={"label": label, "scopes": scopes},
        headers=HDR,
    )
    assert resp.status_code == 200, resp.text
    m = re.search(r"(rt_[A-Za-z0-9_\-]+)", resp.text)
    assert m, "read token not rendered in the reveal"
    return m.group(1)


def register_app(
    client: TestClient,
    *,
    name: str = "Acme Insights",
    redirect: str = "https://acme.example/callback",
    scopes: list[str] | None = None,
) -> tuple[str, str]:
    scopes = scopes or ["read:audits"]
    resp = client.post(
        "/settings/developer/apps",
        data={"name": name, "redirect_uris": redirect, "scopes": scopes},
        headers=HDR,
    )
    assert resp.status_code == 200, resp.text
    cid = re.search(r"(oac_[A-Za-z0-9_\-]+)", resp.text)
    csec = re.search(r"(oas_[A-Za-z0-9_\-]+)", resp.text)
    assert cid and csec
    return cid.group(1), csec.group(1)


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


# ----------------------------------------------------------------- scopes unit


class TestScopes:
    def test_parse_drops_unknown_and_dedupes(self) -> None:
        assert api_scopes.parse_scopes("read:audits read:audits bogus") == ["read:audits"]

    def test_scopes_are_known_requires_all_valid_and_nonempty(self) -> None:
        assert api_scopes.scopes_are_known("read:audits read:findings")
        assert not api_scopes.scopes_are_known("read:audits bogus")
        assert not api_scopes.scopes_are_known("")

    def test_subset(self) -> None:
        assert api_scopes.is_subset("read:audits", "read:audits read:findings")
        assert not api_scopes.is_subset("read:findings", "read:audits")

    def test_no_write_scope_exists(self) -> None:
        assert all(s.startswith("read:") for s in api_scopes.READ_SCOPES)


# ----------------------------------------------------------- API token journey


class TestApiTokenJourney:
    def test_free_plan_cannot_mint(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)  # create the account (free)
        resp = client.post(
            "/settings/developer/tokens",
            data={"label": "x", "scopes": "read:audits"},
            headers=HDR,
        )
        assert resp.status_code == 403 and "/billing" in resp.json()["detail"]

    def test_mint_reveals_once_and_stores_hash_only(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        token = mint_token(client, ["read:audits"])
        with app.state.session_factory() as session:
            row = session.execute(select(ApiToken)).scalar_one()
            assert row.token_hash is not None and token not in row.token_hash
            assert row.scopes == "read:audits"

    def test_read_returns_only_callers_audits_counts_only(self, app: FastAPI) -> None:
        uid = grant(app)
        other = grant(app, email=OTHER)
        mine = seed_audit(app, uid, spend=42.5)
        seed_audit(app, other, spend=999.0)  # another tenant's audit
        client = TestClient(app)
        token = mint_token(client, ["read:audits"])
        resp = client.get("/api/v1/audits", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        ids = {a["id"] for a in body["audits"]}
        assert ids == {mine}  # tenant isolation — never the other user's
        # counts/dollars only, no text fields
        blob = resp.text.lower()
        assert "prompt" not in blob and "completion" not in blob and "content" not in blob
        assert body["audits"][0]["total_spend_usd"] == 42.5
        assert body["audits"][0]["findings"] == 1

    def test_scope_enforced_403_without_findings_scope(self, app: FastAPI) -> None:
        uid = grant(app)
        audit_id = seed_audit(app, uid)
        client = TestClient(app)
        token = mint_token(client, ["read:audits"])  # NOT read:findings
        auth = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/audits", headers=auth).status_code == 200
        r = client.get(f"/api/v1/audits/{audit_id}/findings", headers=auth)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "forbidden"

    def test_findings_scope_reads_findings(self, app: FastAPI) -> None:
        uid = grant(app)
        audit_id = seed_audit(app, uid)
        client = TestClient(app)
        token = mint_token(client, ["read:audits", "read:findings"])
        r = client.get(
            f"/api/v1/audits/{audit_id}/findings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        f = r.json()["findings"][0]
        assert f["detector"] == "d1_model_overkill" and f["monthly_cost_impact_usd"] == 31.0

    def test_other_tenant_audit_is_404_not_403(self, app: FastAPI) -> None:
        grant(app)
        other = grant(app, email=OTHER)
        their_audit = seed_audit(app, other)
        client = TestClient(app)
        token = mint_token(client, ["read:audits", "read:findings"])
        r = client.get(
            f"/api/v1/audits/{their_audit}/findings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404  # existence oracle closed

    def test_no_token_401(self, app: FastAPI) -> None:
        assert TestClient(app).get("/api/v1/audits").status_code == 401

    def test_revoke_stops_the_token(self, app: FastAPI) -> None:
        uid = grant(app)
        seed_audit(app, uid)
        client = TestClient(app)
        token = mint_token(client, ["read:audits"])
        auth = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/audits", headers=auth).status_code == 200
        with app.state.session_factory() as session:
            tid = session.execute(select(ApiToken.id)).scalar_one()
        assert client.post(f"/settings/developer/tokens/{tid}/revoke", headers=HDR).status_code in (
            303,
            200,
        )
        assert client.get("/api/v1/audits", headers=auth).status_code == 401


# ------------------------------------------------------------ reachability


class TestReachability:
    def test_developer_page_renders_with_forms(self, app: FastAPI) -> None:
        grant(app)
        html = TestClient(app).get("/settings/developer", headers=HDR).text
        assert 'hx-post="/settings/developer/tokens"' in html
        assert 'hx-post="/settings/developer/apps"' in html
        assert "read:audits" in html and "read:findings" in html

    def test_developer_reachable_via_the_settings_home(self, app: FastAPI) -> None:
        # O-4: Developer is now a TAB inside the Settings home, not a top-level sidebar
        # item — so reachability is sidebar → Settings → Developer tab.
        grant(app)
        c = TestClient(app)
        assert 'href="/settings"' in c.get("/dashboard", headers=HDR).text  # sidebar → Settings
        settings = c.get("/settings", headers=HDR).text
        assert 'href="/settings/developer"' in settings  # the tab spine links Developer


# ------------------------------------------------------------- OAuth flow


class TestOAuthFlow:
    def _authorize_to_code(
        self, client: TestClient, cid: str, challenge: str, *, redirect: str, scope: str
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": redirect,
            "scope": scope,
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        page = client.get("/oauth/authorize", params=params, headers=HDR)
        assert page.status_code == 200 and "wants" in page.text
        # system-tester note (2026-07-24): drive the REAL rendered form, not
        # hand-constructed field names — a template typo in the hidden field or
        # the approve button must fail the test, not silently break users.
        squashed = re.sub(r"\s+", " ", page.text)
        assert 'name="decision" value="approve"' in squashed
        blob = re.search(r'name="auth_request" value="([^"]+)"', page.text).group(1)
        post = client.post(
            "/oauth/authorize",
            data={"auth_request": blob, "decision": "approve"},
            headers=HDR,
            follow_redirects=False,
        )
        assert post.status_code == 302
        loc = post.headers["location"]
        assert loc.startswith(redirect) and "state=xyz" in loc
        return re.search(r"[?&]code=([^&]+)", loc).group(1)

    def test_full_authorize_exchange_read(self, app: FastAPI) -> None:
        uid = grant(app)
        seed_audit(app, uid)
        client = TestClient(app)
        cid, csec = register_app(client, scopes=["read:audits"])
        verifier, challenge = pkce()
        redirect = "https://acme.example/callback"
        code = self._authorize_to_code(
            client, cid, challenge, redirect=redirect, scope="read:audits"
        )
        tok = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": cid,
                "client_secret": csec,
                "code_verifier": verifier,
            },
        )
        assert tok.status_code == 200, tok.text
        body = tok.json()
        assert body["token_type"] == "Bearer" and body["scope"] == "read:audits"
        access = body["access_token"]
        assert access.startswith("at_")
        r = client.get("/api/v1/audits", headers={"Authorization": f"Bearer {access}"})
        assert r.status_code == 200 and len(r.json()["audits"]) == 1

    def test_unknown_client_shows_error_no_redirect(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        _, challenge = pkce()
        r = client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": "oac_nope",
                "redirect_uri": "https://evil.example/x",
                "scope": "read:audits",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            headers=HDR,
            follow_redirects=False,
        )
        assert r.status_code == 400 and "Unknown application" in r.text
        assert "location" not in r.headers  # never redirected to the attacker URI

    def test_unregistered_redirect_uri_rejected(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        cid, _ = register_app(client, redirect="https://acme.example/callback")
        _, challenge = pkce()
        r = client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": cid,
                "redirect_uri": "https://acme.example/evil",  # not registered
                "scope": "read:audits",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            headers=HDR,
            follow_redirects=False,
        )
        assert r.status_code == 400 and "redirect_uri" in r.text
        assert "location" not in r.headers

    def test_code_is_single_use(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        cid, csec = register_app(client)
        verifier, challenge = pkce()
        redirect = "https://acme.example/callback"
        code = self._authorize_to_code(
            client, cid, challenge, redirect=redirect, scope="read:audits"
        )
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
            "client_id": cid,
            "client_secret": csec,
            "code_verifier": verifier,
        }
        assert client.post("/oauth/token", data=form).status_code == 200
        second = client.post("/oauth/token", data=form)
        assert second.status_code == 400 and second.json()["error"] == "invalid_grant"

    def test_bad_pkce_verifier_rejected(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        cid, csec = register_app(client)
        _, challenge = pkce()
        redirect = "https://acme.example/callback"
        code = self._authorize_to_code(
            client, cid, challenge, redirect=redirect, scope="read:audits"
        )
        r = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": cid,
                "client_secret": csec,
                "code_verifier": "not-the-verifier",
            },
        )
        assert r.status_code == 400 and r.json()["error"] == "invalid_grant"

    def test_non_ascii_verifier_is_invalid_grant_not_500(self, app: FastAPI) -> None:
        """cold-reviewer f.2 (2026-07-24): a non-ASCII code_verifier must be a
        clean invalid_grant, never an uncaught 500 that leaks a distinguishable
        error (the opaque-error invariant)."""
        grant(app)
        client = TestClient(app)
        cid, csec = register_app(client)
        _, challenge = pkce()
        redirect = "https://acme.example/callback"
        code = self._authorize_to_code(
            client, cid, challenge, redirect=redirect, scope="read:audits"
        )
        r = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": cid,
                "client_secret": csec,
                "code_verifier": "café-not-ascii-ñ-☃",
            },
        )
        assert r.status_code == 400 and r.json()["error"] == "invalid_grant"

    def test_consent_form_exposes_real_fields(self, app: FastAPI) -> None:
        """system-tester note (2026-07-24): the rendered consent form must carry
        the exact hidden field and approve button the route reads, so a template
        rename fails the test instead of silently breaking real users."""
        grant(app)
        client = TestClient(app)
        cid, _ = register_app(client, scopes=["read:audits", "read:findings"])
        _, challenge = pkce()
        page = client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": cid,
                "redirect_uri": "https://acme.example/callback",
                "scope": "read:audits read:findings",
                "state": "s",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            headers=HDR,
        )
        squashed = re.sub(r"\s+", " ", page.text)
        assert 'name="auth_request"' in squashed  # the hidden blob the route loads
        assert 'name="decision" value="approve"' in squashed  # the button the route checks
        assert 'name="decision" value="deny"' in squashed
        # the consented scopes are shown to the user in plain language
        assert "read:audits" in squashed and "read:findings" in squashed

    def test_wrong_client_secret_rejected(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        cid, _ = register_app(client)
        verifier, challenge = pkce()
        redirect = "https://acme.example/callback"
        code = self._authorize_to_code(
            client, cid, challenge, redirect=redirect, scope="read:audits"
        )
        r = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": cid,
                "client_secret": "oas_wrong",
                "code_verifier": verifier,
            },
        )
        assert r.status_code == 401 and r.json()["error"] == "invalid_client"

    def test_deny_redirects_with_access_denied(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        cid, _ = register_app(client)
        _, challenge = pkce()
        redirect = "https://acme.example/callback"
        params = {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": redirect,
            "scope": "read:audits",
            "state": "s1",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        page = client.get("/oauth/authorize", params=params, headers=HDR)
        blob = re.search(r'name="auth_request" value="([^"]+)"', page.text).group(1)
        r = client.post(
            "/oauth/authorize",
            data={"auth_request": blob, "decision": "deny"},
            headers=HDR,
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert (
            "error=access_denied" in r.headers["location"] and "state=s1" in r.headers["location"]
        )

    def test_consent_bound_to_owner_csrf(self, app: FastAPI) -> None:
        """The signed blob is minted for EMAIL; a different logged-in user
        (OTHER) submitting it is refused — CSRF + owner binding."""
        grant(app)
        grant(app, email=OTHER)
        client = TestClient(app)
        cid, _ = register_app(client)
        _, challenge = pkce()
        redirect = "https://acme.example/callback"
        params = {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": redirect,
            "scope": "read:audits",
            "state": "s",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        page = client.get("/oauth/authorize", params=params, headers=HDR)
        blob = re.search(r'name="auth_request" value="([^"]+)"', page.text).group(1)
        # OTHER submits EMAIL's blob
        r = client.post(
            "/oauth/authorize",
            data={"auth_request": blob, "decision": "approve"},
            headers=OTHER_HDR,
            follow_redirects=False,
        )
        assert r.status_code == 403 and "location" not in r.headers

    def test_app_revoke_kills_issued_token(self, app: FastAPI) -> None:
        uid = grant(app)
        seed_audit(app, uid)
        client = TestClient(app)
        cid, csec = register_app(client)
        verifier, challenge = pkce()
        redirect = "https://acme.example/callback"
        code = self._authorize_to_code(
            client, cid, challenge, redirect=redirect, scope="read:audits"
        )
        access = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": cid,
                "client_secret": csec,
                "code_verifier": verifier,
            },
        ).json()["access_token"]
        auth = {"Authorization": f"Bearer {access}"}
        assert client.get("/api/v1/audits", headers=auth).status_code == 200
        with app.state.session_factory() as session:
            app_id = session.execute(select(OAuthApp.id)).scalar_one()
        client.post(f"/settings/developer/apps/{app_id}/revoke", headers=HDR)
        assert client.get("/api/v1/audits", headers=auth).status_code == 401

    def test_needs_login_interstitial_when_logged_out(self, app: FastAPI) -> None:
        grant(app)
        client = TestClient(app)
        cid, _ = register_app(client)
        _, challenge = pkce()
        # No auth header at all -> the consent screen asks the owner to sign in.
        r = TestClient(app).get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": cid,
                "redirect_uri": "https://acme.example/callback",
                "scope": "read:audits",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        assert r.status_code == 200 and "Sign in" in r.text
