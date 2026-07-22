"""R-PRICING-FINAL-2 (founder-ratified 2026-07-22) — dual-market pricing.

India ₹499 launch → ₹999 list, Scale ₹4,999 flat; global $19 → $29 and
$59 → $99. Per-market first-200 launch cohorts whose flip to list price is
computed IN CODE from subscription rows; one currency per view with the
other a labeled toggle away; every amount from config. The ruled test,
verbatim: "INR page renders ₹ prices; USD page renders $ prices; no
surface mixes them."

Deliberately allowed on BOTH views: audited-spend gates ("$25K") and the
qualifying threshold ("$500") — AI spend is dollar-denominated even for
Indian buyers (OpenAI/Anthropic bill in USD), so those are spend figures,
not prices.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.persistence.models import Subscription, User
from tokenops_cost_auditor.services.payments import plans, subscriptions
from tokenops_cost_auditor.services.payments.subscriptions import SubscriptionEvent

EMAIL = "pricing@example.com"


def _event(email: str, kind: str, provider: str, eid: str) -> SubscriptionEvent:
    currency = "INR" if provider == "razorpay" else "USD"
    return SubscriptionEvent(
        event_id=eid, email=email, kind=kind, plan="pro", currency=currency, ref=f"sub-{eid}"
    )


def _seed_subscribers(
    app: FastAPI,
    n: int,
    provider: str = "stripe",
    kinds: tuple[str, ...] = ("activated",),
    prefix: str = "cohort",
) -> None:
    """Seed through the REAL webhook path (apply_event) so the append-only
    activation ledger — what cohort_used counts — is written the way
    production writes it."""
    settings = app.state.settings
    with app.state.session_factory() as session:
        for i in range(n):
            email = f"{prefix}-{provider}-{i}@example.com"
            for j, kind in enumerate(kinds):
                subscriptions.apply_event(
                    session, settings, provider, _event(email, kind, provider, f"{prefix}{i}-{j}")
                )
        session.commit()


class TestOneCurrencyPerView:
    def test_usd_default_shows_launch_dollars_and_no_rupee_prices(self, client: TestClient) -> None:
        page = client.get("/").text
        assert "$19/mo" in page  # Pro launch
        assert "$29/mo" in page  # named in the launch note
        assert "$59/mo" in page and "$99/mo" in page  # Scale launch → list
        assert "Launch price for the first 200 subscribers" in page
        for rupee_price in ("₹499", "₹999", "₹14,999", "₹4,999"):
            assert rupee_price not in page, "the USD view must not mix in INR prices"
        assert "Prices include GST." not in page

    def test_india_view_shows_india_dollar_values_with_billed_truth(
        self, client: TestClient
    ) -> None:
        """Founder clarification: SINGLE display currency (dollars) — the
        region changes the VALUE. India sees $4.99/$9.99/$49 (cheaper than
        global at every tier), and the
        rupee amount actually charged is disclosed beside every price."""
        page = client.get("/?ccy=INR").text
        assert "$4.99/mo" in page  # Pro launch, India value
        assert "$9.99/mo" in page  # named in the launch note
        assert "$49/mo" in page  # Scale, India value — cheaper than global $99
        assert "$199" in page  # one-shot, India value
        assert "Billed in India as ₹499/mo incl. GST." in page
        assert "Billed in India as ₹4,999/mo incl. GST." in page
        assert "Billed in India as ₹20,000." in page
        for global_price in ("$19/mo", "$29/mo", "$59/mo", "$99/mo"):
            assert global_price not in page, "the India view must not show global values"

    def test_india_scale_has_no_launch_note(self, client: TestClient) -> None:
        """India Scale is flat ₹4,999 — a launch note on it would be a
        promise of a future raise that isn't ruled."""
        page = client.get("/?ccy=INR").text
        assert page.count("Launch price for the first 200 subscribers") == 1  # Pro only

    def test_indian_locale_defaults_to_the_inr_view(self, client: TestClient) -> None:
        page = client.get("/", headers={"Accept-Language": "en-IN,en;q=0.9"}).text
        assert "$4.99/mo" in page and "$19/mo" not in page

    def test_timezone_detection_drives_the_currency_cookie(self, client: TestClient) -> None:
        """Walkthrough fix: Accept-Language lies (Indian browsers ship en-US)
        so region detection rides the browser CLOCK — India is one timezone.
        The detection script must be on the page, and the server must honor
        the cookie it sets, even under an en-US locale."""
        page = client.get("/").text
        assert "Asia/Kolkata" in page  # the early detection script
        client.cookies.set("ccy", "INR")
        inr = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"}).text
        assert "$4.99/mo" in inr and "$19/mo" not in inr

    def test_explicit_toggle_beats_the_detection_cookie_and_persists(
        self, client: TestClient
    ) -> None:
        client.cookies.set("ccy", "INR")
        page = client.get("/?ccy=USD")
        assert "$19/mo" in page.text and "$4.99/mo" not in page.text
        # the choice sticks: the server rewrites the detection cookie
        assert "ccy=USD" in page.headers.get("set-cookie", "")

    def test_the_qualifying_line_and_anchor_are_on_the_page(self, client: TestClient) -> None:
        page = " ".join(client.get("/").text.split())  # templates wrap lines
        assert "Pro pays for itself" in page  # §5 worth test: self-qualification
        assert "we'll be here when your bill grows" in page
        assert "pays for itself in found waste" in page  # the anchor line
        assert "Covers up to $25K/mo of audited AI spend." in page
        assert "Covers up to $100K/mo of audited AI spend." in page


class TestTheCodeEnforcedFlip:
    def test_a_full_usd_cohort_flips_only_the_usd_view(self, app: FastAPI) -> None:
        _seed_subscribers(app, app.state.settings.launch_cohort_size, provider="stripe")
        client = TestClient(app)
        usd = client.get("/").text
        assert "$29/mo" in usd and "$19/mo" not in usd
        assert "$99/mo" in usd and "$59/mo" not in usd
        assert "Launch price" not in usd, "a filled cohort shows plain list prices — no 'was' talk"
        inr = client.get("/?ccy=INR").text
        assert "$4.99/mo" in inr, "the India cohort is independent and still open"

    def test_cancelled_subscribers_still_consume_cohort_slots(self, app: FastAPI) -> None:
        """'First 200 subscribers', not 'current 200' — churn does not
        reopen launch pricing."""
        _seed_subscribers(app, 3, provider="razorpay")
        _seed_subscribers(
            app, 2, provider="razorpay", kinds=("activated", "cancelled"), prefix="gone"
        )
        with app.state.session_factory() as session:
            assert plans.cohort_used(session, "INR") == 5

    def test_a_failed_never_activated_row_consumes_nothing(self, app: FastAPI) -> None:
        _seed_subscribers(app, 1, provider="stripe", kinds=("failed",), prefix="fail")
        with app.state.session_factory() as session:
            assert plans.cohort_used(session, "USD") == 0

    def test_a_market_switch_cannot_reopen_a_consumed_slot(self, app: FastAPI) -> None:
        """Cold-review f.2: Subscription is ONE mutable row per account, so a
        later provider switch would rewrite row-based history. The cohort is
        counted from the append-only activation ledger instead: an account
        that activated on Stripe and later re-activated on Razorpay keeps a
        slot consumed in BOTH markets, forever."""
        settings = app.state.settings
        with app.state.session_factory() as session:
            email = "switcher@example.com"
            subscriptions.apply_event(
                session, settings, "stripe", _event(email, "activated", "stripe", "sw-1")
            )
            subscriptions.apply_event(
                session, settings, "razorpay", _event(email, "activated", "razorpay", "sw-2")
            )
            session.commit()
            assert plans.cohort_used(session, "USD") == 1, "the Stripe slot stays consumed"
            assert plans.cohort_used(session, "INR") == 1


class TestBillingCurrency:
    def test_a_subscribed_account_sees_its_own_billing_currency(self, app: FastAPI) -> None:
        with app.state.session_factory() as session:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
            session.add(
                Subscription(
                    user_id=user.id,
                    provider="razorpay",
                    plan="pro",
                    status="active",
                    currency="INR",
                )
            )
            session.commit()
        # the toggle cannot talk an INR-billed account into a USD page
        page = TestClient(app).get("/billing?ccy=USD", headers={"X-User-Email": EMAIL}).text
        assert "$4.99/mo" in page and "$19/mo" not in page
        assert "Billed in India as ₹499/mo incl. GST." in page
        assert "Billed in India as ₹20,000." in page  # one-shot follows the account

    def test_signed_in_free_account_gets_the_toggle(self, app: FastAPI) -> None:
        client = TestClient(app)
        usd = client.get("/billing", headers={"X-User-Email": EMAIL}).text
        assert "$19/mo" in usd and "$4.99/mo" not in usd
        inr = client.get("/billing?ccy=INR", headers={"X-User-Email": EMAIL}).text
        assert "$4.99/mo" in inr and "$19/mo" not in inr


class TestConfigOnlyLaw:
    def test_no_ruled_price_literal_lives_in_a_template(self) -> None:
        """Every amount renders from plans.py off Settings; a literal in a
        template drifts the day the founder changes config."""
        for path in Path("src/tokenops_cost_auditor/web/templates").rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            for literal in (
                "$19",
                "$29",
                "$59",
                "$4.99",
                "$9.99",
                "$149",
                "$49",
                "$199",
                "₹499",
                "₹999",
                "₹14,999",
                "₹4,999",
                "₹20,000",
                "₹4,999",
            ):
                assert literal not in text, f"inline price {literal} in {path}"
