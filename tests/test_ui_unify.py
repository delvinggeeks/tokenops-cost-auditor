"""v4 UI unification — the seam between the two design systems.

The app shipped with two shells: app/_shell.html on wa-design.css, and
base.html with its own inline palette for landing, /upload, /sources and
/legal. The designed sidebar linked to /upload and /sources, so the product
navigated its own users out of its own design, and the connect flow crossed
the seam twice. These tests pin it closed.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

TEMPLATES = Path(__file__).parents[1] / "src/tokenops_cost_auditor/web/templates"
DESIGNED = "/static/wa-design.css"


def _consume_link(client, link, follow_redirects=False):
    """GET now only shows a confirm page; POST signs in (readiness audit)."""
    from urllib.parse import parse_qs, urlparse

    token = parse_qs(urlparse(link).query)["token"][0]
    return client.post("/auth/verify", data={"token": token}, follow_redirects=follow_redirects)


class _Recorder:
    def __init__(self) -> None:
        self.magic_links: list[tuple[str, str]] = []

    def magic_link(self, to_email: str, link_url: str) -> None:
        self.magic_links.append((to_email, link_url))

    def report_ready(self, to_email: str, report_url: str) -> None:
        pass


def signed_in(app: FastAPI) -> TestClient:
    """A client holding a real session cookie, obtained through the real
    magic-link flow rather than by forging a cookie — the redirect behaviour
    under test depends on the session actually verifying."""
    recorder = _Recorder()
    app.state.mail = recorder
    # https base URL so the Secure session cookie is sent back (app_env=test
    # drops Secure, but the app-shell pages are the same either way).
    client = TestClient(app, base_url="https://testserver")
    client.post("/auth/signin-link", data={"email": "seam@example.com"})
    _consume_link(client, recorder.magic_links[-1][1])
    return client


class TestNoSurfaceIsLeftOnTheOldShell:
    def test_the_old_shell_is_gone_entirely(self) -> None:
        """base.html carried its own inline palette — the seam. It was retired
        surface by surface; R-LANDING-2 (2026-07-25) moved the last holdout,
        the landing, onto the public shell and DELETED the file. Nothing may
        reference it again, and it must not quietly come back."""
        assert not (TEMPLATES / "base.html").exists(), "base.html rose from the dead"
        stragglers = sorted(
            p.relative_to(TEMPLATES).as_posix()
            for p in TEMPLATES.rglob("*.html")
            # extends/include only — comments recounting the history may say
            # the name; templates may not USE it
            if '"base.html"' in p.read_text(encoding="utf-8")
        )
        assert stragglers == [], f"pages still referencing the retired shell: {stragglers}"

    def test_sources_renders_in_the_designed_shell(self, app: FastAPI) -> None:
        """The whole point of the fix: the sidebar links here, so this page must
        not be a different product when the user arrives."""
        page = signed_in(app).get("/sources").text
        assert DESIGNED in page
        assert 'class="sidebar"' in page

    def test_upload_renders_in_the_designed_shell_when_signed_in(self, app: FastAPI) -> None:
        page = signed_in(app).get("/upload").text
        assert DESIGNED in page and 'class="sidebar"' in page

    def test_legal_pages_render_in_the_public_shell(self, app: FastAPI) -> None:
        client = TestClient(app)
        for path in ("/legal/terms", "/legal/privacy", "/legal/dpa"):
            page = client.get(path).text
            assert DESIGNED in page, path
            assert "/static/wa-public.css" in page, path


class TestSignInSurfaces:
    def test_signed_out_upload_offers_the_public_shell_not_an_empty_sidebar(
        self, app: FastAPI
    ) -> None:
        page = TestClient(app).get("/upload").text
        assert "/static/wa-public.css" in page
        assert 'class="sidebar"' not in page  # no app nav for someone with no account

    def test_login_and_signup_share_the_form_but_not_the_words(self, app: FastAPI) -> None:
        """One mechanism, two audiences: a returning user wants the door, a
        first-timer wants to know what they are walking into."""
        client = TestClient(app)
        login = client.get("/login").text
        signup = client.get("/signup").text
        assert "Log in" in login and "Start free" in signup
        # the reassurance block is for newcomers only
        assert "no card, ever" in signup
        assert "no card, ever" not in login
        # both post to the same magic-link endpoint
        assert login.count('action="/auth/signin-link"') == 1
        assert signup.count('action="/auth/signin-link"') == 1

    def test_signed_in_users_are_sent_to_the_dashboard_not_the_form(self, app: FastAPI) -> None:
        client = signed_in(app)
        for path in ("/login", "/signup"):
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code == 303, path
            assert resp.headers["location"] == "/dashboard", path

    def test_the_magic_link_itself_lands_on_the_dashboard(self, app: FastAPI) -> None:
        """Funnel ruling 3c: every fresh session lands on /dashboard. v1
        landed on /upload — the product led with a form instead of what it
        found. This pins the actual link-click, not just the /login guard."""
        recorder = _Recorder()
        app.state.mail = recorder
        client = TestClient(app, base_url="https://testserver")
        client.post("/auth/signin-link", data={"email": "fresh@example.com"})
        resp = _consume_link(client, recorder.magic_links[-1][1])
        assert resp.status_code == 303
        assert resp.headers["location"] == "/dashboard"


class TestHtmlIsNeverCached:
    def test_html_responses_carry_no_store(self, app: FastAPI) -> None:
        """Every page is session-dependent. A shared cache or a back-button
        could otherwise hand one account's dashboard to the next person."""
        client = TestClient(app)
        for path in ("/", "/login", "/legal/terms"):
            resp = client.get(path)
            assert "no-store" in resp.headers.get("cache-control", ""), path

    def test_static_assets_are_still_cacheable(self, app: FastAPI) -> None:
        """no-store on CSS would re-download the design system on every view."""
        resp = TestClient(app).get("/static/wa-design.css")
        assert resp.status_code == 200
        assert "no-store" not in resp.headers.get("cache-control", "")


class TestEveryStaticReferenceIsVersioned:
    def test_rendered_pages_carry_no_unversioned_statics(self, app: FastAPI) -> None:
        """The stale-cache bug that cost two founder review rounds: an
        unversioned /static/ URL gets neither cache-busting nor no-store —
        browsers heuristic-cache it and a deploy renders under old css/js.
        The gate caught tour.js missed by a hand-sweep; this test makes the
        class structural. Rendered pages, so partials are covered too."""
        import re

        client = signed_in(app)
        pages = [client.get(p).text for p in ("/", "/login", "/dashboard", "/findings")]
        offenders = []
        ref = re.compile(r'(?:src|href|content)="(?:https?://[^"/]+)?(/static/[^"?#]+)(\?[^"]*)?"')
        for html in pages:
            for m in ref.finditer(html):
                if not (m.group(2) or "").startswith("?v="):
                    offenders.append(m.group(1))
        assert not offenders, f"unversioned static references: {sorted(set(offenders))}"
