"""R-SYSTEM-TEST (founder, 2026-07-23) — the journey suite.

The gate agents review each milestone's DIFF; nobody owned walking the whole
product as a user, which is why link-target and staleness bugs reached the
founder. This suite is that role's standing, in-CI half: sign in, render
every app destination, follow every internal link the pages actually emit,
and assert the shell never silently drops the user onto the public landing.

It deliberately reads rendered HTML, not route tables — a link that exists
in code but 404s in a template is exactly the bug class it must catch.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, FindingRow, User

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}

APP_PAGES = (
    "/dashboard",
    "/findings",
    "/explore",
    "/sources",
    "/upload",
    "/alerts",
    "/statements",
    "/settings",
    "/billing",
    "/guide",
    "/activity",
)

HREF = re.compile(r'(?:href|hx-get)="([^"]+)"')
# Never followed: external, anchors, mail, and endpoints that mutate.
SKIP = re.compile(r"^(https?:|mailto:|#|javascript:)")


def seed(app: FastAPI) -> None:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        audit = Audit(
            user_id=user.id,
            status="done",
            row_count=1000,
            observed_days=10,
            total_spend_usd=50.0,
            created_at=datetime.now(UTC),
            report_ready_at=datetime.now(UTC),
        )
        session.add(audit)
        session.flush()
        session.add(
            FindingRow(
                audit_id=audit.id,
                finding_id="D2-001",
                detector="d2_missing_cache",
                route="claude-sonnet-5",
                severity="high",
                monthly_impact_usd=100.0,
                confidence="estimated",
                fix_text="cache it",
                evidence_sample=[{"row_idx": 1, "tokens": 10}],
            )
        )
        session.commit()


class TestEveryPageRenders:
    def test_all_app_destinations_render_inside_the_shell(self, app: FastAPI) -> None:
        seed(app)
        client = TestClient(app)
        for page in APP_PAGES:
            resp = client.get(page, headers=HDR)
            assert resp.status_code == 200, f"{page} -> {resp.status_code}"
            assert 'class="sidebar"' in resp.text, f"{page} escaped the app shell"

    def test_every_emitted_link_resolves(self, app: FastAPI) -> None:
        """Follow every internal href/hx-get the rendered pages emit.
        Anything >= 400 is a broken promise a customer will click."""
        seed(app)
        client = TestClient(app)
        seen: set[str] = set()
        broken: list[str] = []
        for page in APP_PAGES:
            html = client.get(page, headers=HDR).text
            for url in HREF.findall(html):
                if SKIP.match(url) or url in seen:
                    continue
                seen.add(url)
                resp = client.get(url, headers=HDR, follow_redirects=False)
                if resp.status_code >= 400:
                    broken.append(f"{page} -> {url} [{resp.status_code}]")
        assert not broken, "broken links: " + "; ".join(broken)

    def test_app_shell_never_links_back_to_the_landing(self, app: FastAPI) -> None:
        """A signed-in user's 'home' is /dashboard. The shell must not emit a
        bare '/' link that strands them on the public landing (founder
        report, 2026-07-23 — the docs-site round trip)."""
        seed(app)
        client = TestClient(app)
        for page in APP_PAGES:
            html = client.get(page, headers=HDR).text
            assert 'href="/"' not in html, f"{page} links to the public landing"

    def test_docs_link_keeps_the_dashboard_open(self, app: FastAPI) -> None:
        """Documentation opens in a new tab — the app is never navigated away."""
        seed(app)
        html = TestClient(app).get("/dashboard", headers=HDR).text
        m = re.search(r'<a href="[^"]*"[^>]*>(?:<svg[^>]*>.*?</svg>)?Documentation', html)
        assert m is not None
        anchor = html[m.start() : m.start() + 200]
        assert 'target="_blank"' in anchor and 'rel="noopener"' in anchor

    def test_docs_site_offers_the_way_back(self) -> None:
        """The docs nav carries an explicit dashboard link (R-LIVE-DASH):
        clicking around the docs must never maroon a customer off-app."""
        from pathlib import Path

        nav = Path("mkdocs.yml").read_text()
        assert "Your dashboard" in nav and "/dashboard" in nav


class TestNoStaleDashboard:
    def test_every_widget_listens_for_the_landing(self, app: FastAPI) -> None:
        """R-LIVE-DASH: when a run lands, every widget refreshes once — the
        founder must never read yesterday's numbers next to a fresh audit."""
        seed(app)
        html = TestClient(app).get("/dashboard", headers=HDR).text
        listeners = html.count('hx-trigger="audit-landed from:body"')
        assert listeners >= 9, f"only {listeners} widgets listen for audit-landed"

    def test_landing_render_announces_audit_landed(self, app: FastAPI) -> None:
        """The polled pipeline render that catches the transition emits the
        HX-Trigger header; idle and still-running renders do not."""
        seed(app)  # latest audit is done -> a live=1 poll means "just landed"
        client = TestClient(app)
        landed = client.get("/dashboard/w/pipeline?live=1", headers=HDR)
        assert landed.headers.get("HX-Trigger") == "audit-landed"
        idle = client.get("/dashboard/w/pipeline", headers=HDR)
        assert "HX-Trigger" not in idle.headers
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            session.add(Audit(user_id=user.id, status="processing"))
            session.commit()
        running = client.get("/dashboard/w/pipeline?live=1", headers=HDR)
        assert "HX-Trigger" not in running.headers


class TestCrossSurfaceConsistency:
    def test_explorer_never_contradicts_the_dashboard(self, app: FastAPI) -> None:
        """system-tester f.1 (first sweep, 2026-07-23): the seed writes NO
        aggregate rows, and the explorer showed 'No history to explore yet'
        while the dashboard beside it claimed the findings. Two surfaces may
        never disagree about whether history exists."""
        seed(app)
        client = TestClient(app)
        dash = client.get("/dashboard", headers=HDR).text
        assert "1 findings" in dash  # the dashboard's claim...
        exp = client.get("/explore", headers=HDR).text
        assert "No history to explore yet" not in exp
        assert "Findings in this slice — 1" in exp  # ...is the explorer's claim
        assert "no per-day usage" in re.sub(r"\s+", " ", exp)  # honesty about missing data
