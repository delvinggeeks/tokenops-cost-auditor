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
from pathlib import Path

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
    "/runs",
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

    def test_clean_latest_audit_never_denies_history(self, app: FastAPI) -> None:
        """system-tester sweep 2 f.1: a clean audit landing AFTER one with
        findings made the dashboard claim 'clean / 0 applied' while the
        explorer showed the finding. The Report stage now scopes its claim,
        and Act counts APPLIED fixes (verified dollars stay R-Q9-pure)."""
        from tokenops_cost_auditor.persistence.models import FindingFeedback

        seed(app)  # older audit: 1 finding
        client = TestClient(app)
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            older = session.execute(select(Audit)).scalars().one()
            session.add(
                FindingFeedback(
                    audit_id=older.id,
                    finding_id="D2-001",
                    verdict="applied",
                    savings_realized_usd=80.0,
                    actor=EMAIL,
                )
            )
            session.add(  # a newer, clean audit (ran, priced, zero findings)
                Audit(
                    user_id=user.id,
                    status="done",
                    row_count=500,
                    observed_days=8,
                    total_spend_usd=20.0,
                    created_at=datetime.now(UTC),
                    report_ready_at=datetime.now(UTC),
                )
            )
            session.commit()
        dash = re.sub(r"\s+", " ", client.get("/dashboard", headers=HDR).text)
        assert "latest audit clean" in dash  # scoped claim, not account-wide
        assert "earlier finding in your history — see Explore" in dash
        assert "1 applied" in dash  # applied count, not the verified subset
        assert "customer-reported" in dash  # R-Q9: shown separately, never verified
        exp = client.get("/explore", headers=HDR).text
        assert "Findings in this slice — 1" in exp  # surfaces agree

    def test_identified_waste_is_scoped_in_words_on_both_surfaces(self, app: FastAPI) -> None:
        """system-tester C3 walk f.1: with two audits carrying different
        findings, the dashboard's Report note (latest audit) and the
        explorer's waste stat (whole slice) are DIFFERENT true facts — each
        must say which scope it means, or a user reads a 3x contradiction."""
        seed(app)  # audit 1: one $100 finding
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            newer = Audit(
                user_id=user.id,
                status="done",
                row_count=800,
                observed_days=9,
                total_spend_usd=30.0,
                created_at=datetime.now(UTC),
                report_ready_at=datetime.now(UTC),
            )
            session.add(newer)
            session.flush()
            session.add(
                FindingRow(
                    audit_id=newer.id,
                    finding_id="D1-001",
                    detector="d1_oversized_model",
                    route="gpt-4o",
                    severity="med",
                    monthly_impact_usd=15.0,
                    confidence="estimated",
                    fix_text="downsize",
                    evidence_sample=[{"row_idx": 1, "tokens": 5}],
                )
            )
            session.commit()
        client = TestClient(app)
        dash = re.sub(r"\s+", " ", client.get("/dashboard", headers=HDR).text)
        assert "$15.00/mo identified — latest audit" in dash  # scoped
        exp = re.sub(r"\s+", " ", client.get("/explore", headers=HDR).text)
        assert "$115.00/mo" in exp  # the slice's sum ($100 + $15)
        assert "findings in this slice" in exp  # scoped

    def test_peer_opt_out_updates_every_rendered_rank(self, app: FastAPI) -> None:
        """system-tester M-FLY-1 f.5: one customer opting out must reshape
        every OTHER customer's rendered rank — through the real settings
        endpoint, asserted on rendered HTML, so the stale-widget class dies."""
        values = (2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35)
        with app.state.session_factory() as session:
            for i, v in enumerate(values):
                user = User(email=f"c{i}@x.com")
                session.add(user)
                session.flush()
                session.add(
                    Audit(
                        user_id=user.id,
                        status="done",
                        row_count=100,
                        observed_days=10,
                        total_spend_usd=10.0,
                        savings_pct=float(v),
                        created_at=datetime.now(UTC),
                        report_ready_at=datetime.now(UTC),
                    )
                )
            session.commit()
        client = TestClient(app)
        v14 = {"X-User-Email": "c4@x.com"}
        before = re.sub(r"\s+", " ", client.get("/dashboard", headers=v14).text)
        assert "42nd percentile" in before and "based on 12 companies" in before
        # the v=2 customer opts out through the REAL endpoint
        resp = client.post(
            "/settings/benchmarks",
            headers={"X-User-Email": "c0@x.com"},
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        gone = client.get("/dashboard", headers={"X-User-Email": "c0@x.com"}).text
        assert "How you compare" not in gone  # their own widget vanishes
        after = re.sub(r"\s+", " ", client.get("/dashboard", headers=v14).text)
        assert "based on 11 companies" in after  # the pool shrank for everyone
        assert "36th percentile" in after and "leaner than 64%" in after


class TestEveryProviderIsReachable:
    def test_every_shipped_wizard_is_linked_from_sources(self, app: FastAPI) -> None:
        """R-CONNECT-VISIBLE (founder report 2026-07-23): Anthropic's wizard
        existed since WP-1 but NO surface linked it — a shipped connector a
        customer cannot reach does not exist. Every wizard the registry
        declares must be linked wherever connecting is offered, and its page
        must render."""
        from tokenops_cost_auditor.web import help as help_registry

        client = TestClient(app)
        providers = help_registry.wizard_providers()
        assert set(providers) >= {"openai", "anthropic"}
        sources = client.get("/sources", headers=HDR).text
        upload = client.get("/upload", headers=HDR).text
        for prov in providers:
            link = f"/sources/connect/{prov}"
            assert link in sources, f"sources page never offers {prov}"
            assert link in upload, f"get-logs tabs never offer {prov}"
            page = client.get(link, headers=HDR)
            assert page.status_code == 200, f"{link} -> {page.status_code}"
            # the wizard offers the way to every OTHER provider too
            for other in providers:
                if other != prov:
                    assert f"/sources/connect/{other}" in page.text


class TestDeclaredEqualsReachable:
    """R-REACHABILITY (founder question 2026-07-23: 'why didn't the system
    validator catch this?'). Root cause: the crawler verified every link
    pages EMIT — it had no inventory of what the product DECLARES, so a
    shipped capability with zero inbound links (the Anthropic wizard,
    live-but-unlinked since WP-1) was invisible to it. This law closes the
    class: the DECLARED inventory (registry wizards, guide pages, app
    destinations) must be a subset of the crawl closure from /dashboard.
    It fails on the v1.6.1 tree; it must never fail again."""

    def _crawl_closure(self, client, start: str = "/dashboard", limit: int = 150) -> set[str]:
        seen: list[str] = []
        paths: set[str] = set()
        queue = [start]
        while queue and len(seen) < limit:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.append(url)
            r = client.get(url, headers=HDR, follow_redirects=True)
            if r.status_code >= 400:
                continue
            paths.add(url.split("?")[0])
            if "text/html" not in r.headers.get("content-type", ""):
                continue
            for link in HREF.findall(r.text):
                if SKIP.match(link) or link.startswith("/static"):
                    continue
                if link not in seen:
                    queue.append(link)
        return paths

    def test_every_declared_capability_is_reachable_by_clicking(self, app: FastAPI) -> None:
        from tokenops_cost_auditor.web import help as help_registry
        from tokenops_cost_auditor.web.help import _raw

        seed(app)  # data so data-dependent links render
        inventory: set[str] = set(APP_PAGES)
        inventory |= {f"/sources/connect/{p}" for p in help_registry.wizard_providers()}
        inventory |= {f"/guide/{g['slug']}" for g in help_registry.guide_index()}
        inventory |= {
            str(w["link"])
            for w in _raw()["widgets"].values()
            if str(w.get("link", "")).startswith("/guide/")
        }
        closure = self._crawl_closure(TestClient(app))
        unreachable = sorted(inventory - closure)
        assert not unreachable, (
            "shipped capabilities a customer cannot click their way to: " + ", ".join(unreachable)
        )

    def test_every_plan_sees_its_honest_sources_page(self, app: FastAPI) -> None:
        """Blind spot 3: walks always ORM-granted plans, so nobody saw what a
        real Free account sees. Pin each plan's rendered truth."""
        from tokenops_cost_auditor.persistence.models import Subscription

        client = TestClient(app)
        client.get("/dashboard", headers=HDR)  # creates the account
        free = client.get("/sources", headers=HDR).text
        assert "of 1</b> connection" in free  # free = 1 connection, stated
        with app.state.session_factory() as session:
            user = session.execute(select(User).where(User.email == EMAIL)).scalar_one()
            session.add(Subscription(user_id=user.id, provider="manual", plan="team"))
            session.commit()
        team = client.get("/sources", headers=HDR).text
        assert "of 5</b> connection" in team  # team = 5 connections, stated
        for prov in ("openai", "anthropic"):
            assert f"/sources/connect/{prov}" in team


class TestCollectorJourney:
    """system-tester WP-CC-LINK gaps, closed as standing tests: plan-scoped
    rendering (via the ADMIN GRANT product path, not ORM), and the
    device→explorer→findings chain a linking customer actually walks."""

    def test_collector_scopes_by_plan_and_devices_reach_the_explorer(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=HDR)  # create the free account
        free = re.sub(r"\s+", " ", client.get("/sources", headers=HDR).text)
        assert "part of Pro" in free  # honest gate for Free (Q4)
        # the CONTROL is gated (the tells-line prose legitimately renders):
        assert 'hx-post="/sources/claude-code/code"' not in free
        # plan via the PRODUCT path (charter preference): admin grant
        app.state.settings.admin_token = "t-admin"
        granted = client.post(
            "/admin/plans/grant",
            headers={"X-Admin-Token": "t-admin"},
            data={"email": EMAIL, "plan": "team"},
        )
        assert granted.status_code == 200
        pro = client.get("/sources", headers=HDR).text
        assert 'hx-post="/sources/claude-code/code"' in pro
        assert "part of Pro" not in pro
        # link a machine and ship (as the CLI would)
        partial = client.post("/sources/claude-code/code", headers=HDR).text
        code = re.search(r"link ([A-Za-z0-9_\-]+) --server", partial).group(1)
        assert "counts only" in re.sub(r"\s+", " ", partial)  # consent words (Q3)
        token = client.post(
            "/api/v1/collector/link",
            json={"code": code, "hostname": "ci-runner", "consent": True},
        ).json()["device_token"]
        fixture = Path(__file__).parent / "fixtures" / "waste_pack_anthropic.jsonl"
        shipped = client.post(
            "/api/v1/collector/ship",
            files={"file": ("c.jsonl", fixture.read_bytes(), "application/json")},
            headers={"X-Device-Token": token},
        )
        assert shipped.status_code == 201
        # Q1: the explorer's selector NAMES the machine, and its slice narrows
        exp = client.get("/explore", headers=HDR).text
        assert "ci-runner (Claude Code)" in exp
        with app.state.session_factory() as session:
            from tokenops_cost_auditor.persistence.models import Device

            device_id = session.execute(select(Device)).scalars().one().id
        sliced = re.sub(
            r"\s+", " ", client.get("/explore", headers=HDR, params={"source": device_id}).text
        )
        assert "Composed from 1 audits" in sliced
        # Q2: the shipped audit's findings render on /findings
        findings = client.get("/findings", headers=HDR).text
        assert "findings" in findings and 'id="drawer"' in findings
