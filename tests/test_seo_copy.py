"""R-NAME-SEO §2 — the SEO/copy law: no bare "TokenOps" on a public surface.

Every public page's <title>, meta[name=description], and og:title/og:description
must pair "TokenOps" with an AI/LLM/cost qualifier — never market the bare brand
name alone. This is a copy law, not a rename: the fix is always to add a
qualifying word, never to change what a field says.

Two layers:
  * TestPublicRoutesRendered — hits the real routes through the app (TestClient)
    for the pages that need no auth/session setup, so the law is checked against
    what actually ships.
  * TestEveryPublicTemplateSource — sweeps every top-level template outside
    app/ (authenticated) and kit/ (component preview) at the source level, so a
    new public page or a new meta/OG field can't slip past this test without a
    live route being wired up for it.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = Path(__file__).parents[1]
TEMPLATES = REPO / "src/tokenops_cost_auditor/web/templates"

# R-NAME-SEO §2 allowlist — a qualifier that turns "TokenOps" from a bare brand
# name into something that reads as an AI/LLM cost product.
QUALIFIERS = ("Cost Auditor", "AI", "LLM", "spend", "cost")

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
BLOCK_TITLE_RE = re.compile(r"\{%-?\s*block\s+title\s*-?%\}(.*?)\{%-?\s*endblock\s*-?%\}", re.S)


def _meta_content(html: str, key: str, value: str) -> str | None:
    """Find <meta ... key="value" ... content="..." ...> regardless of
    attribute order."""
    pattern = rf'<meta\b(?=[^>]*\b{key}="{re.escape(value)}")(?=[^>]*\bcontent="([^"]*)")[^>]*>'
    m = re.search(pattern, html)
    return m.group(1) if m else None


def assert_tokenops_qualified(value: str, where: str) -> None:
    if "TokenOps" not in value:
        return
    assert any(q in value for q in QUALIFIERS), (
        f"{where} names 'TokenOps' unqualified: {value!r} — must pair it with "
        f"one of {QUALIFIERS} (R-NAME-SEO §2)"
    )


class TestPublicRoutesRendered:
    """The easily-reachable public routes, hit for real through the app."""

    PAGES = ("/", "/sample", "/legal/terms", "/legal/privacy", "/legal/dpa", "/login", "/signup")

    def test_every_page_title_is_qualified(self, app: FastAPI) -> None:
        client = TestClient(app)
        for path in self.PAGES:
            html = client.get(path).text
            m = TITLE_RE.search(html)
            assert m, f"{path}: page has no <title>"
            assert_tokenops_qualified(m.group(1), f"{path} <title>")

    def test_landing_meta_and_og_fields_are_qualified(self, app: FastAPI) -> None:
        """Pins the specific fields the issue flagged: description, og:title,
        og:description — the landing page is the only public surface that sets
        these today, and this is where the og:title gap lived."""
        html = TestClient(app).get("/").text
        description = _meta_content(html, "name", "description")
        og_title = _meta_content(html, "property", "og:title")
        og_description = _meta_content(html, "property", "og:description")
        assert description, "landing has no meta[name=description]"
        assert og_title, "landing has no og:title"
        assert og_description, "landing has no og:description"
        assert_tokenops_qualified(description, "landing meta[description]")
        assert_tokenops_qualified(og_title, "landing og:title")
        assert_tokenops_qualified(og_description, "landing og:description")


class TestEveryPublicTemplateSource:
    """Source-level sweep of every public template, including the ones that
    need auth/session/oauth-request setup to reach via a live route (oauth
    consent/error, the web + PDF report, invite/verify confirmation)."""

    @staticmethod
    def _public_template_paths() -> list[Path]:
        paths = []
        for path in TEMPLATES.rglob("*.html"):
            rel = path.relative_to(TEMPLATES)
            if rel.parts[0] in ("app", "kit"):
                continue  # authenticated app shell / component-kit preview
            if rel.name.startswith("_"):
                continue  # partial/include, not a standalone page
            paths.append(path)
        return sorted(paths)

    def test_discovery_sees_the_known_public_pages(self) -> None:
        """Guards the sweep itself: if template layout changes such that this
        list goes empty or drops a known page, that is a bug in the sweep, not
        a passing test."""
        found = {p.relative_to(TEMPLATES).as_posix() for p in self._public_template_paths()}
        expected = {
            "landing.html",
            "signin.html",
            "invite_accept.html",
            "verify_confirm.html",
            "report.html",
            "legal/terms.html",
            "legal/privacy.html",
            "legal/dpa.html",
            "oauth/authorize.html",
            "oauth/error.html",
            "pdf/report.html",
        }
        assert expected <= found, f"missing from discovery: {expected - found}"

    def test_titles_and_meta_og_are_qualified(self) -> None:
        for path in self._public_template_paths():
            rel = path.relative_to(TEMPLATES).as_posix()
            html = path.read_text(encoding="utf-8")
            title_match = TITLE_RE.search(html) or BLOCK_TITLE_RE.search(html)
            if title_match:
                assert_tokenops_qualified(title_match.group(1), f"{rel} title")
            description = _meta_content(html, "name", "description")
            if description is not None:
                assert_tokenops_qualified(description, f"{rel} meta[description]")
            og_title = _meta_content(html, "property", "og:title")
            if og_title is not None:
                assert_tokenops_qualified(og_title, f"{rel} og:title")
            og_description = _meta_content(html, "property", "og:description")
            if og_description is not None:
                assert_tokenops_qualified(og_description, f"{rel} og:description")
