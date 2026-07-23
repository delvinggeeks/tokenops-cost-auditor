"""T-POL-01..03 (PLAN-V15 V-D9 / WP-7) — the public surfaces.

FR-23 verbatim, the FR-16 sample built by the real engine, and the guided
"get your logs" flow carrying its counts-only promise per route in.
"""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

FR23 = (
    "analyzed then deleted; nothing retained beyond 7 days; "
    "your logs and prompts are never used to train any model"
)
WS = re.compile(r"\s+")


def flat(html: str) -> str:
    """Collapse whitespace: a verbatim string wrapped across template lines is
    still verbatim to a reader, and this is how we check it (the trap that
    bit the D14 sweep)."""
    return WS.sub(" ", html)


class TestPolicyString:
    def test_01_fr23_is_verbatim_and_contiguous_on_every_public_page(self, app: FastAPI) -> None:
        """T-POL-01."""
        client = TestClient(app)
        for path in ("/", "/legal/privacy"):
            assert FR23 in flat(client.get(path).text), path

    def test_upload_page_states_counts_only_before_asking_for_a_file(self, app: FastAPI) -> None:
        page = flat(TestClient(app).get("/upload").text)
        assert "What we receive" in page
        assert page.index("What we receive") < page.index("</form>") or "form" not in page


class TestSampleReport:
    def test_02_sample_is_real_engine_output_not_a_mockup(self, app: FastAPI) -> None:
        """T-POL-02: /sample runs synthetic fixtures through the shipped
        pipeline, so its arithmetic is the product's arithmetic."""
        from tokenops_cost_auditor.services.pricing.table import PricingTable
        from tokenops_cost_auditor.services.report import sample

        resp = TestClient(app).get("/sample")
        assert resp.status_code == 200
        page = flat(resp.text)
        assert "Sample report." in page
        assert "the company is not" in page  # honest about what it is
        # The report carries its OWN data-handling paragraph (DATA_HANDLING);
        # FR-23's verbatim string is the LANDING page's requirement. Asserting
        # the right one on the right surface.
        from tokenops_cost_auditor.services.report.model import DATA_HANDLING

        assert flat(DATA_HANDLING) in page

        model = sample.build_sample(app.state.settings, PricingTable.load())
        assert model.findings, "the sample must contain real findings"
        # every rendered dollar figure comes from the model, not the template
        assert f"{model.monthly_savings_usd:,.2f}" in page.replace("&nbsp;", " ")
        assert model.row_count > 0

    def test_sample_is_deterministic(self, app: FastAPI) -> None:
        client = TestClient(app)
        first, second = client.get("/sample").text, client.get("/sample").text
        assert first == second, "the same fixtures must render the same page"

    def test_sample_needs_no_login(self, app: FastAPI) -> None:
        """It is a marketing artifact: shareable by definition."""
        assert TestClient(app).get("/sample").status_code == 200


class TestGetYourLogsTabs:
    def test_03_every_route_in_carries_its_own_counts_only_promise(self, app: FastAPI) -> None:
        """T-POL-03: the reassurance travels with the instruction."""
        page = flat(TestClient(app).get("/upload").text)
        for tab in (
            "Connect a provider",
            "Claude Code",
            "OpenAI request logs",
            "Anthropic request logs",
            "GitHub Copilot seats",
            "Anything else (CSV)",
        ):
            assert tab in page, tab
        # one "what we receive" line per tab, not a single footer note
        assert page.count("What we receive") == 6  # + GitHub Copilot seats (WP-COPILOT-AGG)
        for promise in (
            "does not contain them",
            "never copies a prompt",
            "content dropped",
            "we ignore it and never store it",
        ):
            assert promise in page, promise

    def test_connect_tab_links_to_the_wizard(self, app: FastAPI) -> None:
        page = TestClient(app).get("/upload").text
        assert "/sources/connect/openai" in page


class TestHeroExperiment:
    def test_both_variants_render_and_stick_per_visitor(self, app: FastAPI) -> None:
        """R-PAINMOMENT: the bill-shock line is tested against the control
        narrative, and a visitor never sees the page change under them.

        Deterministic by construction — a coin-flip assertion has no place in
        a suite that must be reproducible, so each arm is pinned explicitly
        and the bucketing function is exercised directly.
        """
        from tokenops_cost_auditor.web.routes_pages import HERO_COOKIE, HERO_VARIANTS

        for variant, marker in (
            ("control", "Take control of your AI spend."),
            ("billshock", "explain?"),
        ):
            client = TestClient(app)
            client.cookies.set(HERO_COOKIE, variant)
            page = client.get("/").text
            assert marker in page, variant
            # sticky: repeat views do not re-roll
            assert marker in client.get("/").text

        # a fresh visitor is assigned exactly one valid variant, and keeps it
        fresh = TestClient(app)
        assigned = fresh.get("/").cookies.get(HERO_COOKIE)
        assert assigned in HERO_VARIANTS
        again = fresh.get("/")
        assert HERO_COOKIE not in again.cookies or again.cookies[HERO_COOKIE] == assigned

    def test_control_variant_keeps_the_approved_narrative(self, app: FastAPI) -> None:
        client = TestClient(app)
        client.cookies.set("hero_v", "control")
        page = client.get("/").text
        assert "Take control of your AI spend." in page
        assert "79%" in page and "98%" in page  # attributed stats only, unchanged
