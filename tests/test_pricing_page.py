"""Issue #66 — dedicated /pricing page (display-only, no price VALUE changes).

Same price config as landing/billing (services/payments/plans,
R-PRICING-FINAL-2): ONE effective price per plan per region, reachable from
the public nav and a landing CTA, per-plan checkout links config-gated with
the same honest "not switched on" note as /billing.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.persistence.models import Base


class TestPricingPageRendersOneEffectivePricePerPlan:
    def test_usd_default_shows_launch_dollars_and_no_rupee_prices(self, client: TestClient) -> None:
        page = client.get("/pricing").text
        assert page.count("plancard-price") == 3, "Free, Pro, Scale — no jumble of extra cards"
        assert "$19/mo" in page  # Pro launch
        assert "$59/mo" in page and "$99/mo" in page  # Scale launch → list
        assert "No card, ever" in page  # Free
        # both Pro and Scale carry a launch tier in USD (Scale's is INR-only flat)
        assert page.count("Launch price for the first 200 subscribers") == 2
        for rupee_price in ("₹499", "₹999", "₹14,999", "₹4,999"):
            assert rupee_price not in page, "the USD view must not mix in INR prices"

    def test_india_view_shows_india_dollar_values_with_billed_truth(
        self, client: TestClient
    ) -> None:
        page = client.get("/pricing?ccy=INR").text
        assert "$4.99/mo" in page  # Pro launch, India value
        assert "$49/mo" in page  # Scale, India value — flat, no launch note
        assert "$199" in page  # one-shot, India value
        assert "Billed in India as ₹499/mo incl. GST." in page
        assert page.count("Launch price for the first 200 subscribers") == 1  # Pro only
        for global_price in ("$19/mo", "$29/mo", "$59/mo", "$99/mo"):
            assert global_price not in page, "the India view must not show global values"

    def test_currency_toggle_is_a_real_link(self, client: TestClient) -> None:
        usd = client.get("/pricing").text
        assert "/pricing?ccy=INR" in usd
        assert 'class="seg active"' in usd
        inr = client.get("/pricing?ccy=INR").text
        assert "/pricing?ccy=USD" in inr

    def test_one_shot_audit_price_is_shown(self, client: TestClient) -> None:
        page = client.get("/pricing").text
        assert "$500" in page
        assert "one-off audit" in page.lower() or "One-off audit" in page


class TestPricingPageCurrencyToggle:
    """Issue #70 — the visible USD|INR toggle: clicking it sets the `ccy`
    cookie so the choice persists (the honesty rail /pricing already had via
    `?ccy` didn't reach a second page load without the cookie); `?ccy` still
    wins over the cookie (unchanged precedence)."""

    def test_toggle_click_redraws_money_and_sets_the_cookie(self, client: TestClient) -> None:
        response = client.get("/pricing?ccy=INR")
        assert response.status_code == 200
        assert response.cookies.get("ccy") == "INR"
        assert "$4.99/mo" in response.text  # Pro launch, India value — a real render

    def test_cookie_persists_the_choice_on_a_later_visit_with_no_param(
        self, client: TestClient
    ) -> None:
        first = client.get("/pricing?ccy=INR")
        assert first.cookies.get("ccy") == "INR"
        second = client.get("/pricing")  # no ?ccy — the cookie must carry it
        assert "$4.99/mo" in second.text
        assert "$19/mo" not in second.text

    def test_explicit_param_still_wins_over_the_cookie(self, client: TestClient) -> None:
        client.get("/pricing?ccy=INR")  # persist INR
        back_to_usd = client.get("/pricing?ccy=USD")
        assert back_to_usd.cookies.get("ccy") == "USD"
        assert "$19/mo" in back_to_usd.text
        assert "$4.99/mo" not in back_to_usd.text


class TestPricingPageReachability:
    def test_nav_links_to_pricing(self, client: TestClient) -> None:
        for path in ("/", "/pricing", "/login", "/signup"):
            page = client.get(path).text
            assert 'href="/pricing"' in page, f"{path} nav is missing the /pricing link"

    def test_landing_cta_reaches_pricing(self, client: TestClient) -> None:
        landing = client.get("/").text
        assert "/pricing" in landing
        page = client.get("/pricing")
        assert page.status_code == 200

    def test_pricing_page_loads_200(self, client: TestClient) -> None:
        assert client.get("/pricing").status_code == 200


class TestPricingPageCheckoutHonesty:
    def _app(self, tmp_path, **links) -> FastAPI:
        settings = Settings(
            app_env="test",
            secret_key="s",
            database_url=f"sqlite:///{tmp_path / 'pricing.db'}",
            upload_dir=tmp_path / "u",
            report_dir=tmp_path / "r",
            backup_dir=tmp_path / "b",
            _env_file=None,
            **links,
        )
        application = create_app(settings)
        Base.metadata.create_all(application.state.engine)
        return application

    def test_unconfigured_checkout_shows_the_honest_note(self, client: TestClient) -> None:
        page = client.get("/pricing").text
        # Pro and Scale both lack a configured link in the base test settings
        assert page.count("Checkout opens once billing is switched on.") == 2

    def test_configured_checkout_links_to_the_per_plan_url(self, tmp_path) -> None:
        app = self._app(
            tmp_path,
            stripe_payment_link_pro="https://pay.example/PRO",
        )
        try:
            page = TestClient(app).get("/pricing").text
            assert "https://pay.example/PRO" in page
            assert page.count("https://pay.example/PRO") == 1
            # Scale still has no link configured — honest note, never a wrong link
            assert "Checkout opens once billing is switched on." in page
        finally:
            app.state.engine.dispose()


class TestConfigOnlyLawCoversPricingPage:
    def test_no_ruled_price_literal_lives_in_the_pricing_template(self) -> None:
        """The repo-wide sweep in test_pricing_final.py already covers this
        file; this pins it locally so the law is visible from this test's
        name too when it regresses."""
        from pathlib import Path

        text = Path("src/tokenops_cost_auditor/web/templates/pricing.html").read_text(
            encoding="utf-8"
        )
        for literal in ("$19", "$29", "$59", "$4.99", "$9.99", "$49", "$199", "₹499", "₹999"):
            assert literal not in text, f"inline price {literal} in pricing.html"
