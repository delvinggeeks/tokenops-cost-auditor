"""D8 tests — T-AUTH-01..04 (magic link), T-WEB-01 (FR-23 verbatim), legal pages,
T-MAIL-01 (SMTP adapter) per docs/05 §3."""

import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.services.mail.smtp import SmtpMailAdapter

FR23_VERBATIM = (
    "analyzed then deleted; nothing retained beyond 7 days; "
    "your logs and prompts are never used to train any model"
)


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
    resp = client.post("/auth/signin-link", data={"email": email})
    assert resp.status_code == 200
    assert "Check your email" in resp.text
    to, link = mail.magic_links[-1]
    assert to == email
    return link


def _token_of(link: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(link).query)["token"][0]


def consume(client: TestClient, link: str, follow_redirects: bool = False):
    """The sign-in now takes two hops: GET shows a confirm page (harmless to a
    mail scanner's prefetch), POST actually signs in (readiness audit)."""
    return client.post(
        "/auth/verify", data={"token": _token_of(link)}, follow_redirects=follow_redirects
    )


@pytest.mark.verifies_requirement("FR-17")
class TestTAUTH01Issue:
    def test_link_issued_and_logged(self, client: TestClient, mail: MailRecorder) -> None:
        link = request_link(client, mail, "cto@example.com")
        token = parse_qs(urlparse(link).query)["token"][0]
        assert len(token) > 20

    def test_invalid_email_rejected(self, client: TestClient, mail: MailRecorder) -> None:
        resp = client.post("/auth/signin-link", data={"email": "not-an-email"})
        assert resp.status_code == 400
        assert mail.magic_links == []

    def test_auth_endpoint_rate_limited(self, client: TestClient, mail: MailRecorder) -> None:
        last = None
        for _ in range(6):  # limit is 5/minute (NFR-03)
            last = client.post("/auth/signin-link", data={"email": "rl@example.com"})
        assert last is not None and last.status_code == 429


@pytest.mark.verifies_requirement("FR-17")
class TestTAUTH02Consume:
    def test_verify_sets_session_cookie_with_flags(
        self, client: TestClient, mail: MailRecorder
    ) -> None:
        link = request_link(client, mail, "cto@example.com")
        resp = consume(client, link)
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
        consume(sclient, link)  # TestClient keeps the cookie jar
        # no X-User-Email header: the session cookie must authenticate (FR-17)
        resp = sclient.get("/api/v1/audits/nonexistent/status")
        assert resp.status_code == 404  # authenticated; audit genuinely absent
        page = sclient.get("/upload")
        assert "cto@example.com" in page.text  # upload page shows signed-in state


@pytest.mark.verifies_requirement("FR-17")
class TestTAUTH03SingleUse:
    def test_second_consume_rejected(self, client: TestClient, mail: MailRecorder) -> None:
        link = request_link(client, mail, "cto@example.com")
        assert consume(client, link).status_code == 303
        second = consume(client, link)
        assert second.status_code == 400
        assert "already used" in second.text

    def test_get_does_not_consume_so_a_mail_scanner_cannot_burn_the_link(
        self, client: TestClient, mail: MailRecorder
    ) -> None:
        """Readiness audit: corporate mail security prefetches links with GET.
        The GET must only SHOW a confirm page — the human's POST still signs
        in afterwards. Consuming on GET locked out scanned work-email buyers."""
        link = request_link(client, mail, "cto@example.com")
        shown = client.get(link, follow_redirects=False)  # the scanner's prefetch
        assert shown.status_code == 200
        assert "Confirm sign-in" in shown.text
        assert "top_session=" not in shown.headers.get("set-cookie", "")  # nothing consumed
        # the human clicks — the link still works
        assert consume(client, link).status_code == 303


@pytest.mark.verifies_requirement("FR-17")
class TestTAUTH04Expiry:
    def test_expired_link_rejected(
        self, client: TestClient, mail: MailRecorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        link = request_link(client, mail, "cto@example.com")
        real = time.time()
        monkeypatch.setattr(time, "time", lambda: real + 16 * 60)  # 15-min expiry
        resp = consume(client, link)
        assert resp.status_code == 400
        assert "expired" in resp.text


@pytest.mark.verifies_requirement("FR-23")
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


def install_fake_smtp(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Capture every message an adapter sends. Returns the growing list, so a
    test can assert on how many messages went out as well as what was in them."""
    outbox: list[dict[str, object]] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 0) -> None:
            self.endpoint = (host, port)
            self.tls = False
            self.login_user: str | None = None

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def ehlo(self) -> None:
            pass

        def has_extn(self, name: str) -> bool:
            return True

        def starttls(self) -> None:
            self.tls = True

        def login(self, user: str, password: str) -> None:
            self.login_user = user

        def send_message(self, msg) -> None:
            outbox.append(
                {
                    "endpoint": self.endpoint,
                    "tls": self.tls,
                    "login": self.login_user,
                    "to": msg["To"],
                    "from": msg["From"],
                    "subject": msg["Subject"],
                    "body": msg.get_content(),
                }
            )

    import smtplib

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return outbox


def make_adapter() -> SmtpMailAdapter:
    return SmtpMailAdapter(
        "smtp.example.com",
        587,
        "u",
        "p",
        "audits@example.com",
        base_url="https://audit.example.com",
    )


@pytest.mark.verifies_requirement("FR-20")
class TestTMAIL01Smtp:
    def test_smtp_adapter_sends_via_starttls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        outbox = install_fake_smtp(monkeypatch)
        make_adapter().magic_link("cto@example.com", "/auth/verify?token=abc")
        sent = outbox[0]
        assert sent["endpoint"] == ("smtp.example.com", 587)
        assert sent["tls"] is True
        assert sent["to"] == "cto@example.com"
        assert re.search(r"https://audit\.example\.com/auth/verify\?token=abc", str(sent["body"]))

    def test_report_ready_carries_an_absolute_link(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A relative URL in mail is a dead link in a mail client — the base_url
        join is the whole job of this method, and it had no test."""
        outbox = install_fake_smtp(monkeypatch)
        make_adapter().report_ready("cfo@example.com", "/r/abc123")
        assert outbox[0]["subject"] == "Your audit report is ready"
        assert "https://audit.example.com/r/abc123" in str(outbox[0]["body"])

    def test_alert_passes_subject_and_body_through_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outbox = install_fake_smtp(monkeypatch)
        make_adapter().alert("cfo@example.com", "Spend up 40%", "Route /chat doubled.")
        assert outbox[0]["subject"] == "Spend up 40%"
        assert "Route /chat doubled." in str(outbox[0]["body"])
        # the display name reads as a company, not machine mail (founder
        # walkthrough 2026-07-22)
        assert outbox[0]["from"] == "TokenOps Cost Auditor <audits@example.com>"

    def test_workspace_invite_carries_the_workspace_and_absolute_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The invite mail is the invitee's only way in — the workspace name in the
        subject and the absolute accept link are the whole job (coverage debt §3 #9)."""
        outbox = install_fake_smtp(monkeypatch)
        make_adapter().workspace_invite("mate@example.com", "/invite/accept?code=xyz", "Acme Corp")
        sent = outbox[0]
        assert "Acme Corp" in sent["subject"]
        assert sent["to"] == "mate@example.com"
        assert "https://audit.example.com/invite/accept?code=xyz" in str(sent["body"])

    def test_digest_subject_flags_alerts_only_when_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The founder triages this digest by subject line alone. If the ALERTS
        suffix were wrong in either direction the digest would be either noise
        or falsely calm — both make it useless as an ops signal."""
        outbox = install_fake_smtp(monkeypatch)
        adapter = make_adapter()
        adapter.send_digest("ops@example.com", "all quiet\n")
        adapter.send_digest("ops@example.com", "ALERTS: disk 91%\n")
        assert outbox[0]["subject"] == "TokenOps daily digest"
        assert outbox[1]["subject"] == "TokenOps daily digest — ALERTS"


class TestG5F2SameSecondReissue:
    def test_fresh_link_after_login_in_same_second_works(
        self, client: TestClient, mail: MailRecorder
    ) -> None:
        """f.2: login and immediate re-request must not lock the user out."""
        first = request_link(client, mail, "fast@example.com")
        assert consume(client, first).status_code == 303
        second = request_link(client, mail, "fast@example.com")  # same wall-clock second
        assert consume(client, second).status_code == 303


class TestRGTMControlLanding:
    """R-GTM-CONTROL (founder 2026-07-18): control narrative + early-access CTA."""

    def test_control_narrative_leads_and_audit_is_step_one(self, client: TestClient) -> None:
        # R-PAINMOMENT added a hero A/B, so this test must say which variant it
        # is asserting. R-GTM-CONTROL governs the control arm; the bill-shock
        # arm is covered in tests/test_polish.py::TestHeroExperiment.
        client.cookies.set("hero_v", "control")
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

    def _login(self, app: FastAPI) -> object:
        from fastapi.testclient import TestClient

        from tokenops_cost_auditor.web.auth import issue_magic_token

        token = issue_magic_token(app.state.settings.secret_key, "flags@example.com")
        return TestClient(app).post("/auth/verify", data={"token": token}, follow_redirects=False)

    def test_dev_cookie_is_sendable_over_http(self, app: FastAPI) -> None:
        resp = self._login(app)
        header = resp.headers["set-cookie"]
        assert "HttpOnly" in header and "SameSite=lax" in header
        assert "Secure" not in header, "a secure cookie is never sent over http"

    def test_prod_cookie_is_https_only(self, tmp_path: Path) -> None:
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

    def test_test_auth_shim_is_a_failclosed_allowlist(self, tmp_path: Path) -> None:
        """Hardening (loophole hunt 2026-07-27): the X-User-Email dev/test shim is a
        fail-closed ALLOWLIST ({dev,test}), NOT `!= "prod"`. A misnamed/staging/blank env
        must REFUSE the impersonation header (401), never silently open it."""
        from tokenops_cost_auditor.config import Settings
        from tokenops_cost_auditor.main import create_app
        from tokenops_cost_auditor.persistence.models import Base

        for env, shim_open in (
            ("staging", False),  # a real non-prod deployment must NOT carry the shim
            ("production", False),  # a typo for "prod" must NOT open it (the old `!= prod` bug)
            ("qa", False),  # any unknown env is refused
            ("dev", True),
            ("test", True),
        ):
            settings = Settings(
                app_env=env,
                secret_key="p" * 64,
                database_url=f"sqlite:///{tmp_path / ((env or 'blank') + '.db')}",
                upload_dir=tmp_path / "u",
                report_dir=tmp_path / "r",
                backup_dir=tmp_path / "b",
                _env_file=None,
            )
            a = create_app(settings)
            Base.metadata.create_all(a.state.engine)
            r = TestClient(a).get("/api/v1/audits/x/status", headers={"X-User-Email": "x@y.com"})
            if shim_open:
                assert r.status_code != 401, f"{env!r} should accept the dev/test shim"
            else:
                assert r.status_code == 401, f"{env!r} must refuse the impersonation header"
