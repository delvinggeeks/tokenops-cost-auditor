"""D-DOCS tests — legal single-sourcing (MP-9) and docs-site invariants.

The web pages under templates/legal/ are the binding copies; docs-site/legal/
mirrors them. These tests fail when the two drift on the clauses that matter,
and pin the docs-site stats policy (docs/09 §6: attributed figures only).
"""

import re
from pathlib import Path

REPO = Path(__file__).parents[1]
DOCS = REPO / "docs-site"
TEMPLATES = REPO / "src/tokenops_cost_auditor/web/templates/legal"

FR23 = (
    "analyzed then deleted; nothing retained beyond 7 days; "
    "your logs and prompts are never used to train any model"
)


def bold_clauses(markdown_text: str) -> list[str]:
    return re.findall(r"\*\*([^*]+)\*\*", markdown_text)


def strong_clauses(html_text: str) -> list[str]:
    return re.findall(r"<strong>([^<]+)</strong>", html_text)


class TestMP9LegalSingleSourcing:
    def test_privacy_fr23_verbatim_in_both(self) -> None:
        web = (TEMPLATES / "privacy.html").read_text(encoding="utf-8")
        docs = (DOCS / "legal/privacy.md").read_text(encoding="utf-8")
        # the web page uses typographic quotes around the same string
        assert FR23 in web.replace("“", '"').replace("”", '"').replace("\n", " ").replace(
            "  ", " "
        ) or FR23 in re.sub(r"\s+", " ", web)
        assert FR23 in re.sub(r"\s+", " ", docs)

    def test_fr23_verbatim_in_terms_too(self) -> None:
        """Terms PARAPHRASED the data promise — "nothing IS retained… YOUR DATA
        IS never used" — while privacy.html and every other surface quoted the
        canonical string. A binding document restating a published promise in
        its own words is the same defect class as the Terms page quoting a price
        we do not charge, and no test covered it (v4 ux gate f.4)."""
        for path in (
            TEMPLATES / "terms.html",
            DOCS / "legal/terms.md",
        ):
            text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
            assert FR23 in text, f"{path}: FR-23 must appear verbatim, not paraphrased"

    def test_clause_structure_matches(self) -> None:
        """Every bold clause heading on a web legal page appears in its docs mirror."""
        for name in ("terms", "privacy", "dpa"):
            web = re.sub(r"\s+", " ", (TEMPLATES / f"{name}.html").read_text(encoding="utf-8"))
            docs = re.sub(r"\s+", " ", (DOCS / f"legal/{name}.md").read_text(encoding="utf-8"))
            found = strong_clauses(web)
            # Non-vacuity: this loop asserts nothing if the template stops using
            # <strong> for clause headings, so the v4 shell rebuild could have
            # silently disabled the guard rather than failing it.
            assert len(found) >= 5, (
                f"{name}: found only {len(found)} clause headings — the MP-9 guard "
                f"is inspecting <strong> and would pass vacuously if the markup moved"
            )
            for clause in found:
                assert clause in bold_clauses(docs), (
                    f"legal drift: clause {clause!r} on web {name} page missing from "
                    f"docs-site/legal/{name}.md (MP-9 single-sourcing)"
                )

    def test_price_matches_terms(self) -> None:
        """Both legal copies must quote the price the CONFIG charges.

        This test used to pin the literal '$500 / ₹20,000' in both files. That
        passed happily while the shipped config rendered ₹45,000 at checkout —
        the test was pinning the two mirrors to each other and to a rate we do
        not charge, so it certified agreement on a wrong number. It now derives
        the expected string from the one price config, which is the only
        version of this check that can catch drift (V-D10).
        """
        from tokenops_cost_auditor.config import Settings
        from tokenops_cost_auditor.services.payments import plans

        expected = plans.one_shot_display(Settings())  # e.g. "$500 · ₹45,000"
        web = (TEMPLATES / "terms.html").read_text(encoding="utf-8")
        docs = (DOCS / "legal/terms.md").read_text(encoding="utf-8")
        # The web page renders the price from config; the static docs mirror
        # cannot, so it carries the literal and must be updated when it moves.
        assert "{{ one_shot }}" in web, "terms.html must render the price from the price config"
        assert expected in docs, (
            f"docs-site/legal/terms.md quotes a price the config does not charge; expected "
            f"{expected!r}. Update the mirror in the same commit as any price change (MP-9)."
        )


class TestDocsSiteStatsPolicy:
    def test_only_attributed_stats_no_banned_figures(self) -> None:
        """docs/09 §6: 79/31/98 must carry attribution; 40-60% and 73% are banned."""
        for page in DOCS.rglob("*.md"):
            text = page.read_text(encoding="utf-8")
            assert "40-60%" not in text and "40\u201360%" not in text, page  # en-dash variant
            assert "73%" not in text, page
            if "79%" in text or "98%" in text:
                assert "DoiT" in text or "State of FinOps" in text, (
                    f"{page}: market stat used without attribution (docs/09 §6)"
                )

    def test_fr23_verbatim_on_home(self) -> None:
        assert FR23 in (DOCS / "index.md").read_text(encoding="utf-8")

    def test_measurement_pending_never_carries_numbers(self) -> None:
        """Every MP admonition must not contain a dollar/timing figure (invented
        numbers = FAIL per DOCS-PLAN)."""
        for page in DOCS.rglob("*.md"):
            text = page.read_text(encoding="utf-8")
            for block in re.findall(
                r'!!! warning "MEASUREMENT-PENDING[^"]*"\n((?:    .*\n?)+)', text
            ):
                assert not re.search(r"\$\d|\d+ ?minutes", block), (
                    f"{page}: MEASUREMENT-PENDING block contains a number"
                )


class TestDocsLinksReachTheDocs:
    """Walkthrough punch 2026-07-22 ("there is no docs"): the docs site was
    live and healthy, but every product link pointed at /docs-site/ — a path
    the app never serves — so no visitor could reach it. Links now come from
    ONE config origin."""

    def test_no_page_links_the_dead_relative_path(self, app, client) -> None:
        docs_url = app.state.settings.docs_url
        for path in ("/", "/login", "/upload", "/dashboard"):
            page = client.get(
                path, headers={"X-User-Email": "docs@example.com"}, follow_redirects=True
            ).text
            assert "/docs-site/" not in page, f"{path} still links the dead path"
        # the nav actually reaches the docs origin on public and app shells
        assert docs_url in client.get("/").text
        assert (
            docs_url in client.get("/dashboard", headers={"X-User-Email": "docs@example.com"}).text
        )


class TestApiReferenceAccuracy:
    """The curated API reference must match the REAL app — so it can't drift
    into documenting a contract the code doesn't honor (founder 2026-07-24)."""

    REF = (DOCS / "api/reference.md").read_text(encoding="utf-8")

    def test_01_documents_the_real_ingest_endpoint_and_auth(self) -> None:
        assert "POST /api/v1/ingest" in self.REF
        assert "Authorization: Bearer ik_" in self.REF  # the real auth scheme
        assert "TOKENOPS_COST_AUDITOR_DSN" in self.REF  # R-NAMING full env var

    def test_02_error_codes_match_the_code(self) -> None:
        from tokenops_cost_auditor.main import ERROR_CODES

        # every documented code string must be a real one the app emits
        for code in (
            "unauthorized",
            "payment_required",
            "payload_too_large",
            "validation_error",
            "rate_limited",
            "internal_error",
        ):
            assert code in ERROR_CODES.values() and code in self.REF

    def test_03_has_multi_language_examples(self) -> None:
        # Anthropic-style language tabs (pymdownx.tabbed)
        for lang in ('=== "curl"', '=== "Python (requests)"', '=== "TypeScript"', '=== "Go"'):
            assert lang in self.REF

    def test_04_states_the_counts_only_contract_not_overclaimed(self) -> None:
        assert "counts-only" in self.REF or "counts only" in self.REF
        assert "rejected" in self.REF  # FR-22 door, honestly described
        # write-only key claim matches S-0's real trust boundary
        assert "write-only" in self.REF

    def test_05_in_nav(self) -> None:
        mk = (REPO / "mkdocs.yml").read_text(encoding="utf-8")
        assert "api/reference.md" in mk

    def test_06_every_documented_route_is_really_registered(self, app) -> None:
        """spec-guard coverage note (2026-07-24): the reference documents the
        ingest, status, report-retrieval and webhook surfaces. Pin each one
        against the REAL app route table so a doc can't outlive its route.
        Routers are lazily wrapped as _IncludedRouter — walk into their
        original_router so nested paths are counted, not just the top level."""

        def walk(routes):
            for r in routes:
                orig = getattr(r, "original_router", None)
                if orig is not None:
                    yield from walk(orig.routes)
                    continue
                p = getattr(r, "path", None)
                if p:
                    yield p

        paths = set(walk(app.routes))
        for documented in (
            "/api/v1/ingest",
            "/api/v1/audits/{audit_id}/status",
            "/api/v1/audits",  # S-6 read endpoint
            "/api/v1/audits/{audit_id}/findings",  # S-6 read endpoint
            "/oauth/authorize",  # S-6 OAuth
            "/oauth/token",  # S-6 OAuth
            "/r/{token}",
            "/r/{token}/pdf",
            "/api/v1/webhooks/stripe",
            "/api/v1/webhooks/razorpay",
        ):
            assert documented in paths, f"reference.md documents a dead route: {documented}"
            # and the doc actually names the surface (guards silent doc drift)
            assert documented.split("{")[0].rstrip("/") in self.REF or documented in self.REF

    def test_07_status_body_documents_optional_keys(self) -> None:
        """cold-reviewer f.2 (2026-07-24): valid_pct/queue_position/error are
        conditional in routes_upload.py — the doc must mark them optional so an
        integrator never KeyErrors coding to a fixed shape."""
        body = re.sub(r"\s+", " ", self.REF)
        assert "absent while the audit is still" in body  # valid_pct optionality
        assert "queue_position" in body and "only" in body
        assert "Code to the presence of each key" in body

    def test_08_documents_the_integer_range_bound(self) -> None:
        """cold-reviewer f.3 (2026-07-24): the [0, _MAX_COUNT] ceiling was
        undocumented. Pin the real bound so the field table can't drop it."""
        from tokenops_cost_auditor.web.routes_ingest import _MAX_COUNT

        assert f"{_MAX_COUNT:,}" in self.REF  # 1,000,000,000,000 stated verbatim

    def test_09_sdk_tag_precedence_is_honest(self) -> None:
        """cold-reviewer f.1 (2026-07-24): init() folds environment/tag into one
        tag (tag wins); the doc must not imply both are captured."""
        body = re.sub(r"\s+", " ", self.REF)
        assert "fold into the" in body and "single" in body
        assert "tag" in body and "wins" in body

    def test_10_read_scopes_match_the_code(self) -> None:
        """S-6: the documented read scopes must be EXACTLY the ones the app
        enforces — no phantom scope, no missing one, no write scope."""
        from tokenops_cost_auditor.web.api_scopes import READ_SCOPES

        for scope in READ_SCOPES:
            assert f"`{scope}`" in self.REF  # every real scope is documented
        # and the doc never invents a scope the code doesn't know
        for doc_scope in re.findall(r"`(read:[a-z]+)`", self.REF):
            assert doc_scope in READ_SCOPES, f"reference.md documents a phantom scope: {doc_scope}"
        assert all(s.startswith("read:") for s in READ_SCOPES)  # no write scope exists

    def test_11_oauth_and_403_documented(self) -> None:
        """S-6: the OAuth authorization-code + PKCE flow and the new 403
        (forbidden = valid token, missing scope) are in the reference."""
        from tokenops_cost_auditor.main import ERROR_CODES

        assert ERROR_CODES[403] == "forbidden" and "forbidden" in self.REF
        body = re.sub(r"\s+", " ", self.REF)
        assert "/oauth/authorize" in body and "/oauth/token" in body
        assert "PKCE" in body and "code_challenge_method=S256" in body
        assert "single-use" in body  # the auth-code single-use guarantee

    # Issue #52 AC-6: the current developer-facing /api/v1 surface, one row
    # per (method, path) — kept in sync with the ISSUE's declared list, not
    # every /api/v1 route (device-collector link/ship is a separate surface
    # out of this slice's scope).
    REQUIRED_V1_ENDPOINTS = (
        ("POST", "/api/v1/ingest"),
        ("POST", "/api/v1/audits"),
        ("GET", "/api/v1/audits"),
        ("GET", "/api/v1/audits/{audit_id}/status"),
        ("GET", "/api/v1/audits/{audit_id}/findings"),
    )

    def test_12_every_current_v1_endpoint_documented_by_method(self, app) -> None:
        """Doc-coverage guard, VERB-aware: unlike test_06 (which only checks a
        bare path is documented somewhere), this pins that reference.md names
        each endpoint as 'METHOD path' — so a new method landing on an
        existing path (e.g. POST /api/v1/audits alongside GET /api/v1/audits)
        can't silently ship undocumented (Issue #52 acceptance criterion 6)."""

        def walk(routes):
            for r in routes:
                orig = getattr(r, "original_router", None)
                if orig is not None:
                    yield from walk(orig.routes)
                    continue
                p = getattr(r, "path", None)
                methods = getattr(r, "methods", None) or set()
                if p:
                    for m in methods - {"HEAD", "OPTIONS"}:
                        yield m, p

        real = set(walk(app.routes))
        for method, path in self.REQUIRED_V1_ENDPOINTS:
            assert (method, path) in real, (
                f"{method} {path} is not a real route — the coverage list is stale"
            )
            assert f"{method} {path}" in self.REF, (
                f"reference.md does not document '{method} {path}'"
            )


class TestMcpDocs:
    """Issue #54 AC-5: the MCP server page — install, client config, the two
    read tools, in the nav — and it can't drift from the real tool set."""

    MCP = (DOCS / "api/mcp.md").read_text(encoding="utf-8")

    def test_in_nav(self) -> None:
        mk = (REPO / "mkdocs.yml").read_text(encoding="utf-8")
        assert "api/mcp.md" in mk

    def test_documents_the_token_env_var_and_command(self) -> None:
        from tokenops_cost_auditor.mcp.server import SERVER_ENV, TOKEN_ENV

        assert TOKEN_ENV in self.MCP
        assert SERVER_ENV in self.MCP
        assert "tokenops-cost-auditor mcp" in self.MCP
        assert "python -m tokenops_cost_auditor.mcp" in self.MCP.replace('"', "")

    def test_documents_both_client_configs(self) -> None:
        assert "Claude Desktop" in self.MCP and "Cursor" in self.MCP
        assert "mcpServers" in self.MCP

    def test_tool_table_matches_the_real_tool_set(self) -> None:
        from tokenops_cost_auditor.mcp.server import TOOLS

        names = {t["name"] for t in TOOLS}
        assert names == {"list_audits", "list_findings"}
        for name in names:
            assert f"`{name}`" in self.MCP
        for scope in ("read:audits", "read:findings"):
            assert f"`{scope}`" in self.MCP

    def test_states_read_only_no_write_tools(self) -> None:
        body = re.sub(r"\s+", " ", self.MCP)
        assert "read-only" in body
        assert "Write tools" in body and "None" in body

    def test_states_fr22_counts_only(self) -> None:
        body = re.sub(r"\s+", " ", self.MCP)
        assert "counts and dollars only" in body.lower() or "counts-only" in body.lower()


class TestSdkJsDocs:
    """R-PLATFORM slice 4: the JS/TS SDK page — install, both credentials, the real
    endpoints + scopes it calls, counts-only — in the nav, so it can't drift."""

    SDK = (DOCS / "api/sdk-js.md").read_text(encoding="utf-8")

    def test_in_nav(self) -> None:
        assert "api/sdk-js.md" in (REPO / "mkdocs.yml").read_text(encoding="utf-8")

    def test_install_and_both_credentials(self) -> None:
        assert "npm install tokenops-cost-auditor" in self.SDK
        assert "ingestKey" in self.SDK and "readToken" in self.SDK
        assert "ik_" in self.SDK and "rt_" in self.SDK

    def test_documents_the_real_endpoints_and_scopes(self) -> None:
        for path in ("/api/v1/ingest", "/api/v1/audits", "/api/v1/audits/{id}/findings"):
            assert path in self.SDK, path
        for scope in ("read:audits", "read:findings"):
            assert scope in self.SDK, scope

    def test_states_counts_only_fr22(self) -> None:
        body = re.sub(r"\s+", " ", self.SDK).lower()
        assert "counts-only" in body or "counts only" in body
        assert "fr-22" in body


class TestWebhooksDocs:
    """Issue #56 — outbound webhooks: register, payload schema, and the HMAC
    verification snippet, in the nav and consistent with the real headers."""

    WH = (DOCS / "api/webhooks.md").read_text(encoding="utf-8")

    def test_in_nav(self) -> None:
        mk = (REPO / "mkdocs.yml").read_text(encoding="utf-8")
        assert "api/webhooks.md" in mk

    def test_documents_the_real_headers_and_event(self) -> None:
        from tokenops_cost_auditor.services.webhooks.dispatcher import (
            EVENT_AUDIT_COMPLETED,
            EVENT_HEADER,
            SIGNATURE_HEADER,
        )

        assert SIGNATURE_HEADER in self.WH
        assert EVENT_HEADER in self.WH
        assert EVENT_AUDIT_COMPLETED in self.WH

    def test_has_a_verification_code_snippet(self) -> None:
        assert "hmac.new(" in self.WH
        assert "hmac.compare_digest(" in self.WH

    def test_states_fr22_no_text(self) -> None:
        body = re.sub(r"\s+", " ", self.WH).lower()
        assert "prompt" in body and "completion" in body
        assert "fr-22" in body

    def test_states_best_effort_no_retry_queue(self) -> None:
        body = re.sub(r"\s+", " ", self.WH).lower()
        assert "best-effort" in body
        assert "never delays or blocks the audit" in body


class TestDeveloperGettingStartedAndTutorial:
    """Issue #52 ACs 1 and 4: a <=5-step minimal integration, and a runnable
    send->poll->read tutorial, both reachable from the docs nav."""

    GETTING_STARTED = (DOCS / "api/getting-started.md").read_text(encoding="utf-8")
    TUTORIAL = (DOCS / "api/tutorial.md").read_text(encoding="utf-8")

    def test_both_pages_in_nav(self) -> None:
        mk = (REPO / "mkdocs.yml").read_text(encoding="utf-8")
        assert "api/getting-started.md" in mk
        assert "api/tutorial.md" in mk

    def test_getting_started_is_five_steps_or_fewer(self) -> None:
        steps = re.findall(r"^## \d+\. ", self.GETTING_STARTED, flags=re.MULTILINE)
        assert 1 <= len(steps) <= 5, (
            f"getting-started.md has {len(steps)} numbered steps — AC-1 caps it at 5"
        )

    def test_getting_started_mints_a_key_and_calls_ingest(self) -> None:
        assert "Mint an ingest key" in self.GETTING_STARTED
        assert "/api/v1/ingest" in self.GETTING_STARTED
        assert "https://tokenops-cost-auditor.com" in self.GETTING_STARTED

    def test_tutorial_walks_send_poll_read(self) -> None:
        body = re.sub(r"\s+", " ", self.TUTORIAL)
        assert "/api/v1/ingest" in body
        assert "/api/v1/audits" in body
        assert "findings" in body and "status" in body
        assert '=== "curl"' in self.TUTORIAL and '=== "Python"' in self.TUTORIAL
