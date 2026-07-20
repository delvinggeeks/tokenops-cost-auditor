"""D8 tests — T-AUTH-01..04 (magic link), T-WEB-01 (FR-23 verbatim), legal pages,
T-MAIL-01 (SMTP adapter) per docs/05 §3."""

import re
import time
from urllib.parse import parse_qs, urlparse

import pytest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.services.mail.smtp import SmtpMailAdapter

FR23_VERBATIM = "analyzed then deleted; nothing retained beyond 7 days; never used for training"


class MailRecorder:
    def __init__(self) -> None:
        self.magic_links: list[tuple[str, str]] = []
        self.reports: list[tuple[str, str]] = []

    def magic_link(self, to_email: str, link_url: str) -> None:
        self.magic_links.append((to_email, link_url))

    def report_ready(self, to_email: str, report_url: str) -> None:
        self.reports.append((to_email, report_url))


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def sclient(app: FastAPI) -> TestClient:
    """https base URL so the Secure session cookie is actually sent back."""
    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def mail(app: FastAPI) -> MailRecorder:
    recorder = MailRecorder()
    app.state.mail = recorder
    app.state.runner.mail = recorder
    return recorder


def request_link(client: TestClient, mail: MailRecorder, email: str) -> str:
    resp = client.post("/auth/magic-link", data={"email": email})
    assert resp.status_code == 200
    assert "Check your email" in resp.text
    to, link = mail.magic_links[-1]
    assert to == email
    return link


class TestTAUTH01Issue:
    def test_link_issued_and_logged(self, client: TestClient, mail: MailRecorder) -> None:
        link = request_link(client, mail, "cto@example.com")
        token = parse_qs(urlparse(link).query)["token"][0]
        assert len(token) > 20

    def test_invalid_email_rejected(self, client: TestClient, mail: MailRecorder) -> None:
        resp = client.post("/auth/magic-link", data={"email": "not-an-email"})
        assert resp.status_code == 400
        assert mail.magic_links == []

    def test_auth_endpoint_rate_limited(self, client: TestClient, mail: MailRecorder) -> None:
        last = None
        for _ in range(6):  # limit is 5/minute (NFR-03)
            last = client.post("/auth/magic-link", data={"email": "rl@example.com"})
        assert last is not None and last.status_code == 429


class TestTAUTH02Consume:
    def test_verify_sets_session_cookie_with_flags(
        self, client: TestClient, mail: MailRecorder
    ) -> None:
        link = request_link(client, mail, "cto@example.com")
        resp = client.get(link, follow_redirects=False)
        assert resp.status_code == 303
        set_cookie = resp.headers["set-cookie"]
        assert "top_session=" in set_cookie
        assert "HttpOnly" in set_cookie  # T-AUTH-04 cookie flags
        assert "SameSite=lax" in set_cookie or "SameSite=Lax" in set_cookie
        # Secure is environment-scoped, not dropped: this fixture is app_env=test,
        # where a Secure cookie would never be sent back over http and the user
        # would sign in only to appear signed out. The production assertion
        # lives in TestSessionCookieFlags::test_prod_cookie_is_https_only.
        assert "Secure" not in set_cookie

    def test_session_authenticates_api_without_header(
        self, sclient: TestClient, mail: MailRecorder, app: FastAPI
    ) -> None:
        link = request_link(sclient, mail, "cto@example.com")
        sclient.get(link, follow_redirects=False)  # TestClient keeps the cookie jar
        # no X-User-Email header: the session cookie must authenticate (FR-17)
        resp = sclient.get("/api/v1/audits/nonexistent/status")
        assert resp.status_code == 404  # authenticated; audit genuinely absent
        page = sclient.get("/upload")
        assert "cto@example.com" in page.text  # upload page shows signed-in state


class TestTAUTH03SingleUse:
    def test_second_consume_rejected(self, client: TestClient, mail: MailRecorder) -> None:
        link = request_link(client, mail, "cto@example.com")
        assert client.get(link, follow_redirects=False).status_code == 303
        second = client.get(link, follow_redirects=False)
        assert second.status_code == 400
        assert "already used" in second.text


class TestTAUTH04Expiry:
    def test_expired_link_rejected(
        self, client: TestClient, mail: MailRecorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        link = request_link(client, mail, "cto@example.com")
        real = time.time()
        monkeypatch.setattr(time, "time", lambda: real + 16 * 60)  # 15-min expiry
        resp = client.get(link, follow_redirects=False)
        assert resp.status_code == 400
        assert "expired" in resp.text


class TestTWEB01Landing:
    def test_fr23_string_verbatim(self, client: TestClient) -> None:
        page = client.get("/")
        assert page.status_code == 200
        assert FR23_VERBATIM in page.text

    def test_one_primary_cta_and_approved_stats_only(self, client: TestClient) -> None:
        html = client.get("/").text
        assert html.count('class="cta"') == 1  # exactly one primary CTA
        assert "79%" in html and "98%" in html  # attributed figures only
        assert "40-60" not in html  # banned per docs/09 §6
        assert "40\u201360" not in html  # en-dash variant
        assert "73%" not in html

    def test_legal_pages_render(self, client: TestClient) -> None:
        for path, marker in (
            ("/legal/terms", "Terms of Service"),
            ("/legal/privacy", FR23_VERBATIM),
            ("/legal/dpa", "Data Processing"),
        ):
            page = client.get(path)
            assert page.status_code == 200, path
            assert marker in page.text, path

    def test_upload_page_logged_out_shows_login(self, client: TestClient) -> None:
        page = client.get("/upload")
        assert page.status_code == 200
        assert "sign-in link" in page.text
        assert "15 minutes" in page.text  # magic-link copy states what happens next


class TestTMAIL01Smtp:
    def test_smtp_adapter_sends_via_starttls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent: dict[str, object] = {}

        class FakeSMTP:
            def __init__(self, host: str, port: int, timeout: int = 0) -> None:
                sent["endpoint"] = (host, port)

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def ehlo(self) -> None:
                pass

            def has_extn(self, name: str) -> bool:
                return True

            def starttls(self) -> None:
                sent["tls"] = True

            def login(self, user: str, password: str) -> None:
                sent["login"] = user

            def send_message(self, msg) -> None:
                sent["to"] = msg["To"]
                sent["subject"] = msg["Subject"]
                sent["body"] = msg.get_content()

        import smtplib

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        adapter = SmtpMailAdapter(
            "smtp.example.com",
            587,
            "u",
            "p",
            "audits@example.com",
            base_url="https://audit.example.com",
        )
        adapter.magic_link("cto@example.com", "/auth/verify?token=abc")
        assert sent["endpoint"] == ("smtp.example.com", 587)
        assert sent["tls"] is True
        assert sent["to"] == "cto@example.com"
        assert re.search(r"https://audit\.example\.com/auth/verify\?token=abc", str(sent["body"]))


class TestG5F2SameSecondReissue:
    def test_fresh_link_after_login_in_same_second_works(
        self, client: TestClient, mail: MailRecorder
    ) -> None:
        """f.2: login and immediate re-request must not lock the user out."""
        first = request_link(client, mail, "fast@example.com")
        assert client.get(first, follow_redirects=False).status_code == 303
        second = request_link(client, mail, "fast@example.com")  # same wall-clock second
        assert client.get(second, follow_redirects=False).status_code == 303


class TestRGTMControlLanding:
    """R-GTM-CONTROL (founder 2026-07-18): control narrative + early-access CTA."""

    def test_control_narrative_leads_and_audit_is_step_one(self, client: TestClient) -> None:
        html = client.get("/").text
        assert "Take control of your AI spend." in html
        assert "step one" in html  # audit framed as step one of a prevention path
        assert html.count('class="cta"') == 1  # audit stays the ONLY primary CTA

    def test_early_access_cta_verbatim_no_promises(self, client: TestClient) -> None:
        html = client.get("/").text
        assert "AI spend control — APIs, agents, and AI seats." in html  # verbatim
        assert 'action="/early-access"' in html
        # no dates, no shipping promises in the block
        assert "coming soon" not in html.lower() and "launching" not in html.lower()

    def test_signup_recorded_in_audit_log(self, client: TestClient, app: FastAPI) -> None:
        resp = client.post("/early-access", data={"email": "Buyer@Corp.com"})
        assert resp.status_code == 200
        assert "on the list" in resp.text
        from sqlalchemy import select

        from tokenops_cost_auditor.persistence.models import AuditLogEntry

        with app.state.session_factory() as session:
            rows = [
                e
                for e in session.scalars(
                    select(AuditLogEntry).where(AuditLogEntry.action == "early_access.signup")
                )
            ]
        assert len(rows) == 1 and rows[0].subject == "buyer@corp.com"

    def test_invalid_email_rejected(self, client: TestClient) -> None:
        assert client.post("/early-access", data={"email": "nope"}).status_code == 400


class TestSessionCookieFlags:
    """The session cookie must be HTTPS-only in production and usable on a
    local http preview — found when the founder preview signed in and
    immediately appeared signed out (2026-07-22)."""

    def _login(self, app: "FastAPI") -> object:
        from fastapi.testclient import TestClient

        from tokenops_cost_auditor.web.auth import issue_magic_token

        token = issue_magic_token(app.state.settings.secret_key, "flags@example.com")
        return TestClient(app).get(f"/auth/verify?token={token}", follow_redirects=False)

    def test_dev_cookie_is_sendable_over_http(self, app: "FastAPI") -> None:
        resp = self._login(app)
        header = resp.headers["set-cookie"]
        assert "HttpOnly" in header and "SameSite=lax" in header
        assert "Secure" not in header, "a secure cookie is never sent over http"

    def test_prod_cookie_is_https_only(self, tmp_path: "Path") -> None:
        from tokenops_cost_auditor.config import Settings
        from tokenops_cost_auditor.main import create_app
        from tokenops_cost_auditor.persistence.models import Base

        settings = Settings(
            app_env="prod",
            secret_key="p" * 64,
            database_url=f"sqlite:///{tmp_path / 'prod.db'}",
            upload_dir=tmp_path / "u",
            report_dir=tmp_path / "r",
            backup_dir=tmp_path / "b",
            _env_file=None,
        )
        prod_app = create_app(settings)
        Base.metadata.create_all(prod_app.state.engine)
        resp = self._login(prod_app)
        assert "Secure" in resp.headers["set-cookie"]
