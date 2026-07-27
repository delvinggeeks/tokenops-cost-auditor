"""Issue #81 — Stripe Subscriptions checkout for recurring USD Pro/Team.

Verified flow: server creates the Checkout Session FIRST (POST
/v1/checkout/sessions, mode=subscription, HTTP Basic Auth, form-encoded body,
inline price_data with a recurring interval, unit_amount in cents built from
OUR pricing config) -> the browser gets a 303 redirect straight to Stripe's
hosted page -> the EXISTING customer.subscription.created webhook
(services/payments/stripe_link.py, services/payments/subscriptions.py, both
reused unchanged from WP-6) is the SOLE activation authority, idempotent on
the Stripe event id -> reflected in the user's entitlements.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.obs.ratelimit import limiter
from tokenops_cost_auditor.persistence.models import Base, Subscription
from tokenops_cost_auditor.services.payments import stripe_subscriptions, subscriptions

STRIPE_SECRET_KEY = "sk_test_123abc"
STRIPE_WEBHOOK_SECRET = "stripe-webhook-secret-2"
BUYER = "buyer@company.com"


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    kwargs = dict(
        app_env="test",
        secret_key="k" * 64,
        database_url=f"sqlite:///{tmp_path / 'stripesub.db'}",
        upload_dir=tmp_path / "u",
        report_dir=tmp_path / "r",
        backup_dir=tmp_path / "b",
        stripe_secret_key=STRIPE_SECRET_KEY,
        stripe_webhook_secret=STRIPE_WEBHOOK_SECRET,
        plan_pro_usd=29.0,
        plan_team_usd=99.0,
        _env_file=None,
    )
    kwargs.update(overrides)
    return Settings(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def sapp(tmp_path: Path) -> Iterator[FastAPI]:
    app = create_app(_settings(tmp_path))
    Base.metadata.create_all(app.state.engine)
    yield app
    app.state.engine.dispose()


@pytest.fixture
def sclient(sapp: FastAPI) -> TestClient:
    return TestClient(sapp)


HDR = {"X-User-Email": BUYER}


def _fake_session_response(session_id: str = "cs_sub_ABC123") -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "id": session_id,
        "url": f"https://checkout.stripe.com/c/pay/{session_id}",
    }
    return resp


def _create_subscription_via_route(
    client: TestClient, plan: str = "pro", session_id: str = "cs_sub_ABC123"
):
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.return_value = _fake_session_response(session_id)
    with patch(
        "tokenops_cost_auditor.services.payments.stripe_subscriptions.httpx.Client",
        return_value=fake_client,
    ):
        resp = client.post(
            "/billing/stripe/subscription", headers=HDR, data={"plan": plan}, follow_redirects=False
        )
    return resp, fake_client


def _webhook_sign(body: bytes, t: int) -> str:
    v1 = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(), f"{t}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return f"t={t},v1={v1}"


def _sub_created_event(
    subscription_id: str, email: str = BUYER, plan: str = "pro", eid: str = "evt_sub_1"
) -> bytes:
    return json.dumps(
        {
            "id": eid,
            "type": "customer.subscription.created",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": subscription_id,
                    "currency": "usd",
                    "metadata": {"email": email, "plan": plan},
                    "status": "active",
                }
            },
        }
    ).encode()


def _post_webhook(client: TestClient, body: bytes, t: int | None = None):
    t = t if t is not None else int(time.time())
    return client.post(
        "/api/v1/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": _webhook_sign(body, t)},
    )


class TestSessionCreate:
    """Test 1: mock the httpx boundary — never hit the network in CI. The
    session amount must equal OUR config USD amount (price-integrity rail),
    never a dashboard-entered figure."""

    def test_pro_request_shape_and_redirect(self, sclient: TestClient) -> None:
        resp, fake_client = _create_subscription_via_route(sclient, plan="pro")
        assert resp.status_code == 303, resp.text
        assert resp.headers["location"] == "https://checkout.stripe.com/c/pay/cs_sub_ABC123"

        assert fake_client.post.call_count == 1
        args, kwargs = fake_client.post.call_args
        assert args[0] == stripe_subscriptions.CHECKOUT_URL
        assert kwargs["auth"] == (STRIPE_SECRET_KEY, "")
        payload = kwargs["data"]
        assert payload["mode"] == "subscription"
        assert payload["line_items[0][price_data][currency]"] == "usd"
        assert payload["line_items[0][price_data][unit_amount]"] == "2900"  # USD 29 -> cents
        assert payload["line_items[0][price_data][recurring][interval]"] == "month"
        assert payload["line_items[0][price_data][product_data][name]"] == "Pro"
        assert payload["line_items[0][quantity]"] == "1"
        assert payload["customer_email"] == BUYER
        assert payload["metadata[user_email]"] == BUYER
        assert payload["metadata[plan]"] == "pro"
        # propagates onto the Subscription object — the key the reused
        # webhook parser reads (StripeLinkAdapter.parse_subscription_event).
        assert payload["subscription_data[metadata][email]"] == BUYER
        assert payload["subscription_data[metadata][plan]"] == "pro"
        assert payload["success_url"].startswith(
            "https://tokenops-cost-auditor.com/billing?checkout=success&session_id="
        )
        assert "{CHECKOUT_SESSION_ID}" in payload["success_url"]
        assert (
            payload["cancel_url"] == "https://tokenops-cost-auditor.com/billing?checkout=cancelled"
        )

    def test_team_amount_matches_config(self, sclient: TestClient) -> None:
        resp, fake_client = _create_subscription_via_route(sclient, plan="team")
        assert resp.status_code == 303
        _, kwargs = fake_client.post.call_args
        assert kwargs["data"]["line_items[0][price_data][unit_amount]"] == "9900"  # 99 -> cents
        assert kwargs["data"]["line_items[0][price_data][product_data][name]"] == "Scale"
        assert kwargs["data"]["metadata[plan]"] == "team"

    def test_unknown_plan_rejected(self, sclient: TestClient) -> None:
        resp = sclient.post(
            "/billing/stripe/subscription", headers=HDR, data={"plan": "enterprise"}
        )
        assert resp.status_code == 400

    def test_session_create_error_surfaces_502(self, sclient: TestClient) -> None:
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.post.return_value = MagicMock(status_code=401, json=lambda: {})
        with patch(
            "tokenops_cost_auditor.services.payments.stripe_subscriptions.httpx.Client",
            return_value=fake_client,
        ):
            resp = sclient.post("/billing/stripe/subscription", headers=HDR, data={"plan": "pro"})
        assert resp.status_code == 502


class TestFullJourney:
    """Test 2: create-session -> signed customer.subscription.created webhook
    -> subscription ACTIVE (via apply_event, reused) -> reflected in
    entitlements/plan. A bad Stripe-Signature grants nothing."""

    def test_journey_activates_via_webhook_and_reflects_in_plan(
        self, sclient: TestClient, sapp: FastAPI
    ) -> None:
        resp, _ = _create_subscription_via_route(sclient, plan="team", session_id="cs_journey1")
        assert resp.status_code == 303
        with sapp.state.session_factory() as session:
            assert session.scalar(select(Subscription)) is None  # not yet — webhook activates it

        webhook_resp = _post_webhook(
            sclient, _sub_created_event("sub_journey1", plan="team", eid="evt_journey_sub")
        )
        assert webhook_resp.status_code == 200
        assert webhook_resp.json() == {"status": "processed"}
        with sapp.state.session_factory() as session:
            sub = session.scalar(select(Subscription))
            assert sub is not None
            assert sub.provider == "stripe" and sub.external_ref == "sub_journey1"
            assert sub.plan == "team" and sub.status == subscriptions.ACTIVE

        billing_page = sclient.get("/billing?ccy=USD", headers=HDR)
        assert billing_page.status_code == 200
        assert "current" in billing_page.text  # the Scale row now shows "current"

    def test_bad_signature_400_and_activates_nothing(
        self, sclient: TestClient, sapp: FastAPI
    ) -> None:
        body = _sub_created_event("sub_bad1", eid="evt_bad_sub")
        resp = sclient.post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )
        assert resp.status_code == 400
        with sapp.state.session_factory() as session:
            assert session.scalar(select(Subscription)) is None


class TestIdempotency:
    """Test 3: a re-delivered customer.subscription.created (same event id)
    activates the subscription exactly once."""

    def test_redelivered_event_activates_once(self, sclient: TestClient, sapp: FastAPI) -> None:
        body = _sub_created_event("sub_dup1", plan="pro", eid="evt_dup_sub_shared")
        first = _post_webhook(sclient, body)
        second = _post_webhook(sclient, body)  # re-delivered, same event id
        assert first.json() == {"status": "processed"}
        assert second.json() == {"status": "duplicate"}
        with sapp.state.session_factory() as session:
            subs = list(session.scalars(select(Subscription)))
        assert len(subs) == 1
        assert subs[0].external_ref == "sub_dup1"


class TestHonestState:
    """Test 4: key unset -> disabled 'not switched on'; cancel_url -> honest
    cancelled state; a subscribed account shows its locked plan, never a
    Subscribe button for its own tier."""

    def test_billing_page_shows_disabled_note_without_key(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, stripe_secret_key=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        page = client.get("/billing?ccy=USD", headers=HDR)
        assert page.status_code == 200
        assert "Checkout opens once billing is switched on." in page.text
        assert 'action="/billing/stripe/subscription"' not in page.text
        app.state.engine.dispose()

    def test_billing_page_shows_subscribe_forms_when_configured(self, sclient: TestClient) -> None:
        page = sclient.get("/billing?ccy=USD", headers=HDR)
        assert page.status_code == 200
        assert page.text.count('action="/billing/stripe/subscription"') == 2
        assert 'name="plan" value="pro"' in page.text
        assert 'name="plan" value="team"' in page.text

    def test_create_subscription_disabled_without_key(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, stripe_secret_key=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        resp = client.post("/billing/stripe/subscription", headers=HDR, data={"plan": "pro"})
        assert resp.status_code == 503
        app.state.engine.dispose()

    def test_cancel_redirect_shows_honest_cancelled_state(self, sclient: TestClient) -> None:
        page = sclient.get("/billing?ccy=USD&checkout=cancelled", headers=HDR)
        assert page.status_code == 200
        assert "Checkout cancelled — nothing was charged." in page.text

    def test_subscribed_account_shows_locked_plan_not_a_subscribe_form(
        self, sclient: TestClient, sapp: FastAPI
    ) -> None:
        webhook_resp = _post_webhook(
            sclient, _sub_created_event("sub_locked1", plan="pro", eid="evt_locked_sub")
        )
        assert webhook_resp.json()["status"] == "processed"
        page = sclient.get("/billing", headers=HDR)  # no ?ccy — currency is LOCKED
        assert page.status_code == 200
        assert "current" in page.text
        # a subscribed account never sees the Subscribe form for its own tier
        assert 'name="plan" value="pro"' not in page.text


class TestSubscriptionsModuleUnit:
    """create_session exercised directly (no FastAPI) — the injected-client
    path and the missing-id/url response shape."""

    def test_create_session_with_injected_client(self) -> None:
        fake = MagicMock()
        fake.post.return_value = _fake_session_response("cs_direct1")
        session = stripe_subscriptions.create_session(
            STRIPE_SECRET_KEY,
            29.0,
            "Pro",
            "pro",
            success_url="https://example.com/s",
            cancel_url="https://example.com/c",
            email="a@b.com",
            client=fake,
        )
        assert session == {
            "id": "cs_direct1",
            "url": "https://checkout.stripe.com/c/pay/cs_direct1",
        }
        _, kwargs = fake.post.call_args
        assert kwargs["auth"] == (STRIPE_SECRET_KEY, "")
        assert kwargs["data"]["line_items[0][price_data][unit_amount]"] == "2900"

    def test_response_missing_id_or_url_raises(self) -> None:
        fake = MagicMock()
        fake.post.return_value = MagicMock(status_code=200, json=lambda: {"id": "cs_x"})
        with pytest.raises(stripe_subscriptions.CheckoutCreateError):
            stripe_subscriptions.create_session(
                STRIPE_SECRET_KEY,
                29.0,
                "Pro",
                "pro",
                success_url="https://example.com/s",
                cancel_url="https://example.com/c",
                email="a@b.com",
                client=fake,
            )


STRIPE_LIVE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")


@pytest.mark.integration
@pytest.mark.skipif(
    not STRIPE_LIVE_SECRET_KEY,
    reason="STRIPE_SECRET_KEY not set — skipped outside a live test-key run",
)
def test_live_create_subscription_session_against_stripe() -> None:
    """Test 5 (key-gated): proves the TEST key + request shape really work
    against api.stripe.com. Never runs in normal CI (no env secret there)."""
    with httpx.Client(timeout=30.0) as client:
        session = stripe_subscriptions.create_session(
            STRIPE_LIVE_SECRET_KEY,
            1.0,
            "CI Pro",
            "pro",
            success_url="https://tokenops-cost-auditor.com/billing?checkout=success",
            cancel_url="https://tokenops-cost-auditor.com/billing?checkout=cancelled",
            email="ci@tokenops-cost-auditor.com",
            client=client,
        )
    assert session["id"].startswith("cs_")
    assert session["url"].startswith("https://checkout.stripe.com/")
