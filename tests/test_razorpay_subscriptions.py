"""Issue #79 — Razorpay Subscriptions checkout for recurring INR Pro/Scale.

Verified flow: server creates the plan (amount from OUR pricing config —
price-integrity rail) then the subscription referencing it (POST /v1/plans,
POST /v1/subscriptions, Basic Auth) -> client opens checkout.js against the
subscription_id -> the modal's signed callback is checked server-side for
UX only (B1), on the payment_id|subscription_id order (opposite of the
one-time order's order_id|payment_id) -> the ALREADY-EXISTING
subscription.activated webhook + subscriptions.apply_event (WP-6, reused
unchanged) is the sole activation authority.
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
from tokenops_cost_auditor.services.payments import razorpay_subscriptions, subscriptions

RZP_KEY_ID = "rzp_test_key123"
RZP_KEY_SECRET = "rzp-test-key-secret"
RZP_WEBHOOK_SECRET = "rzp-webhook-secret"
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
        database_url=f"sqlite:///{tmp_path / 'rzpsub.db'}",
        upload_dir=tmp_path / "u",
        report_dir=tmp_path / "r",
        backup_dir=tmp_path / "b",
        razorpay_key_id=RZP_KEY_ID,
        razorpay_key_secret=RZP_KEY_SECRET,
        razorpay_webhook_secret=RZP_WEBHOOK_SECRET,
        plan_pro_inr=999.0,
        plan_team_inr=4999.0,
        _env_file=None,
    )
    kwargs.update(overrides)
    return Settings(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def rapp(tmp_path: Path) -> Iterator[FastAPI]:
    app = create_app(_settings(tmp_path))
    Base.metadata.create_all(app.state.engine)
    yield app
    app.state.engine.dispose()


@pytest.fixture
def rclient(rapp: FastAPI) -> TestClient:
    return TestClient(rapp)


HDR = {"X-User-Email": BUYER}


def _fake_plan_response(plan_id: str = "plan_ABC123") -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": plan_id}
    return resp


def _fake_sub_response(subscription_id: str = "sub_ABC123") -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": subscription_id}
    return resp


def _create_subscription_via_route(
    client: TestClient,
    plan: str = "pro",
    plan_id: str = "plan_ABC123",
    subscription_id: str = "sub_ABC123",
) -> tuple:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.side_effect = [
        _fake_plan_response(plan_id),
        _fake_sub_response(subscription_id),
    ]
    with patch(
        "tokenops_cost_auditor.services.payments.razorpay_subscriptions.httpx.Client",
        return_value=fake_client,
    ):
        resp = client.post("/billing/razorpay/subscription", headers=HDR, data={"plan": plan})
    return resp, fake_client


def _handler_sign(payment_id: str, subscription_id: str) -> str:
    # Independent fixture computation (R-PAY convention): the provider
    # formula, not the adapter code under test. payment_id FIRST.
    return hmac.new(
        RZP_KEY_SECRET.encode(), f"{payment_id}|{subscription_id}".encode(), hashlib.sha256
    ).hexdigest()


def _webhook_sign(body: bytes) -> str:
    return hmac.new(RZP_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _sub_activated_event(
    subscription_id: str, email: str = BUYER, plan: str = "pro", eid: str = "evt_sub_1"
) -> bytes:
    return json.dumps(
        {
            "event": "subscription.activated",
            "id": eid,
            "created_at": int(time.time()),
            "payload": {
                "subscription": {
                    "entity": {
                        "id": subscription_id,
                        "notes": {"email": email, "plan": plan},
                        "status": "active",
                    }
                }
            },
        }
    ).encode()


def _post_webhook(client: TestClient, body: bytes, sig: str | None = None):
    return client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": sig if sig is not None else _webhook_sign(body)},
    )


class TestPlanAndSubscriptionCreate:
    """Test 1: mock the httpx boundary — never hit the network in CI. The
    plan amount must equal OUR config INR amount (price-integrity rail),
    never a dashboard figure."""

    def test_pro_request_shape_and_response(self, rclient: TestClient) -> None:
        resp, fake_client = _create_subscription_via_route(rclient, plan="pro")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["subscription_id"] == "sub_ABC123"
        assert body["key_id"] == RZP_KEY_ID

        assert fake_client.post.call_count == 2
        plan_args, plan_kwargs = fake_client.post.call_args_list[0]
        assert plan_args[0] == razorpay_subscriptions.PLANS_URL
        assert plan_kwargs["auth"] == (RZP_KEY_ID, RZP_KEY_SECRET)
        plan_payload = plan_kwargs["json"]
        assert plan_payload["period"] == "monthly"
        assert plan_payload["interval"] == 1
        assert plan_payload["item"]["currency"] == "INR"
        # price-integrity rail: OUR config amount (999 INR), not a
        # dashboard-entered figure.
        assert plan_payload["item"]["amount"] == 99900

        sub_args, sub_kwargs = fake_client.post.call_args_list[1]
        assert sub_args[0] == razorpay_subscriptions.SUBSCRIPTIONS_URL
        sub_payload = sub_kwargs["json"]
        assert sub_payload["plan_id"] == "plan_ABC123"  # references the plan just created
        assert sub_payload["notes"]["email"] == BUYER
        assert sub_payload["notes"]["plan"] == "pro"
        assert sub_payload["total_count"] == razorpay_subscriptions.TOTAL_COUNT

    def test_team_amount_matches_config(self, rclient: TestClient) -> None:
        resp, fake_client = _create_subscription_via_route(rclient, plan="team")
        assert resp.status_code == 200, resp.text
        _, plan_kwargs = fake_client.post.call_args_list[0]
        assert plan_kwargs["json"]["item"]["amount"] == 499900  # 4999 INR -> paise

    def test_unknown_plan_rejected(self, rclient: TestClient) -> None:
        resp = rclient.post(
            "/billing/razorpay/subscription", headers=HDR, data={"plan": "enterprise"}
        )
        assert resp.status_code == 400

    def test_provider_error_surfaces_502(self, rclient: TestClient) -> None:
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.post.return_value = MagicMock(status_code=401, json=lambda: {})
        with patch(
            "tokenops_cost_auditor.services.payments.razorpay_subscriptions.httpx.Client",
            return_value=fake_client,
        ):
            resp = rclient.post("/billing/razorpay/subscription", headers=HDR, data={"plan": "pro"})
        assert resp.status_code == 502


class TestSignatureVerify:
    """Test 2: real HMAC, valid vs tampered, on the payment_id|subscription_id
    order — the OPPOSITE of the one-time order's order_id|payment_id. A
    signature built with the one-time order MUST fail here (guards the
    razorpay-node issue #124 gotcha)."""

    def test_valid_signature_verified(self, rclient: TestClient) -> None:
        payment_id, subscription_id = "pay_valid1", "sub_valid1"
        sig = _handler_sign(payment_id, subscription_id)
        resp = rclient.post(
            "/billing/razorpay/subscription/verify",
            headers=HDR,
            data={
                "razorpay_payment_id": payment_id,
                "razorpay_subscription_id": subscription_id,
                "razorpay_signature": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "verified"}

    def test_tampered_signature_400(self, rclient: TestClient) -> None:
        resp = rclient.post(
            "/billing/razorpay/subscription/verify",
            headers=HDR,
            data={
                "razorpay_payment_id": "pay_bad1",
                "razorpay_subscription_id": "sub_bad1",
                "razorpay_signature": "deadbeef",
            },
        )
        assert resp.status_code == 400

    def test_one_time_order_signature_order_is_rejected(self, rclient: TestClient) -> None:
        """The gotcha guard: a signature computed with the ONE-TIME order's
        `order_id|payment_id` order must NOT verify here."""
        payment_id, subscription_id = "pay_flip1", "sub_flip1"
        wrong_order_sig = hmac.new(
            RZP_KEY_SECRET.encode(),
            f"{subscription_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        resp = rclient.post(
            "/billing/razorpay/subscription/verify",
            headers=HDR,
            data={
                "razorpay_payment_id": payment_id,
                "razorpay_subscription_id": subscription_id,
                "razorpay_signature": wrong_order_sig,
            },
        )
        assert resp.status_code == 400

    def test_verify_disabled_without_secret(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, razorpay_key_secret=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        resp = client.post(
            "/billing/razorpay/subscription/verify",
            headers=HDR,
            data={
                "razorpay_payment_id": "p",
                "razorpay_subscription_id": "s",
                "razorpay_signature": "x",
            },
        )
        assert resp.status_code == 503
        app.state.engine.dispose()


class TestFullJourney:
    """Test 3: create-sub -> handler-POST (200, UX only, no activation yet)
    -> signed subscription.activated webhook (THE activation authority,
    reused from WP-6) -> reflected in the user's entitlements."""

    def test_journey_activates_via_webhook_and_reflects_in_entitlements(
        self, rclient: TestClient, rapp: FastAPI
    ) -> None:
        resp, _ = _create_subscription_via_route(
            rclient, plan="team", subscription_id="sub_journey1"
        )
        subscription_id = resp.json()["subscription_id"]

        sig = _handler_sign("pay_journey1", subscription_id)
        verify_resp = rclient.post(
            "/billing/razorpay/subscription/verify",
            headers=HDR,
            data={
                "razorpay_payment_id": "pay_journey1",
                "razorpay_subscription_id": subscription_id,
                "razorpay_signature": sig,
            },
        )
        assert verify_resp.status_code == 200 and verify_resp.json()["status"] == "verified"
        with rapp.state.session_factory() as session:
            # B1: a valid handler signature is UX-only — no activation yet.
            assert session.scalar(select(Subscription)) is None

        webhook_resp = _post_webhook(
            rclient, _sub_activated_event(subscription_id, plan="team", eid="evt_journey_sub")
        )
        assert webhook_resp.status_code == 200 and webhook_resp.json()["status"] == "processed"

        with rapp.state.session_factory() as session:
            sub = session.scalar(select(Subscription))
            assert sub is not None
            assert sub.plan == "team" and sub.status == subscriptions.ACTIVE
            assert sub.external_ref == subscription_id

        billing_page = rclient.get("/billing?ccy=INR", headers=HDR)
        assert billing_page.status_code == 200
        assert "current" in billing_page.text  # the Scale row now shows "current"

    def test_tampered_handler_signature_400_and_activates_nothing(
        self, rclient: TestClient, rapp: FastAPI
    ) -> None:
        resp, _ = _create_subscription_via_route(rclient, plan="pro", subscription_id="sub_tamper1")
        subscription_id = resp.json()["subscription_id"]
        bad_resp = rclient.post(
            "/billing/razorpay/subscription/verify",
            headers=HDR,
            data={
                "razorpay_payment_id": "pay_tamper1",
                "razorpay_subscription_id": subscription_id,
                "razorpay_signature": "not-the-real-signature",
            },
        )
        assert bad_resp.status_code == 400
        with rapp.state.session_factory() as session:
            assert session.scalar(select(Subscription)) is None


class TestHonestState:
    """Test 4: key/secret unset -> disabled 'not switched on'; an already-
    subscribed account shows its locked plan, never a Subscribe modal."""

    def test_billing_page_shows_disabled_note_without_keys(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, razorpay_key_id="", razorpay_key_secret=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        page = client.get("/billing?ccy=INR", headers=HDR)
        assert page.status_code == 200
        assert "Checkout opens once billing is switched on." in page.text
        assert 'class="btn btn-primary rzp-sub-btn"' not in page.text
        app.state.engine.dispose()

    def test_billing_page_shows_subscribe_buttons_when_configured(
        self, rclient: TestClient
    ) -> None:
        page = rclient.get("/billing?ccy=INR", headers=HDR)
        assert page.status_code == 200
        assert 'class="btn btn-primary rzp-sub-btn"' in page.text
        assert 'data-plan="pro"' in page.text
        assert 'data-plan="team"' in page.text

    def test_subscribed_account_shows_locked_plan_not_a_modal(
        self, rclient: TestClient, rapp: FastAPI
    ) -> None:
        webhook_resp = _post_webhook(
            rclient, _sub_activated_event("sub_locked1", plan="pro", eid="evt_locked_sub")
        )
        assert webhook_resp.json()["status"] == "processed"
        page = rclient.get("/billing", headers=HDR)  # no ?ccy — currency is LOCKED
        assert page.status_code == 200
        assert "current" in page.text
        # a subscribed account never sees the Subscribe button for its own tier
        assert 'data-plan="pro"' not in page.text

    def test_create_subscription_disabled_without_keys(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, razorpay_key_id="", razorpay_key_secret=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        resp = client.post("/billing/razorpay/subscription", headers=HDR, data={"plan": "pro"})
        assert resp.status_code == 503
        app.state.engine.dispose()


class TestSubscriptionsModuleUnit:
    """create_plan/create_subscription/verify_sub_signature exercised
    directly (no FastAPI)."""

    def test_create_plan_with_injected_client(self) -> None:
        fake = MagicMock()
        fake.post.return_value = _fake_plan_response("plan_direct1")
        plan = razorpay_subscriptions.create_plan(
            RZP_KEY_ID, RZP_KEY_SECRET, "Pro", 999.0, client=fake
        )
        assert plan == {"plan_id": "plan_direct1", "amount": 99900, "currency": "INR"}
        _, kwargs = fake.post.call_args
        assert kwargs["auth"] == (RZP_KEY_ID, RZP_KEY_SECRET)

    def test_create_subscription_with_injected_client(self) -> None:
        fake = MagicMock()
        fake.post.return_value = _fake_sub_response("sub_direct1")
        sub = razorpay_subscriptions.create_subscription(
            RZP_KEY_ID, RZP_KEY_SECRET, "plan_direct1", "a@b.com", "pro", client=fake
        )
        assert sub == {"subscription_id": "sub_direct1"}
        _, kwargs = fake.post.call_args
        assert kwargs["json"]["plan_id"] == "plan_direct1"
        assert kwargs["json"]["notes"] == {"email": "a@b.com", "plan": "pro"}

    def test_verify_sub_signature_real_hmac_payment_id_first(self) -> None:
        sig = hmac.new(b"sekret", b"p1|s1", hashlib.sha256).hexdigest()
        assert razorpay_subscriptions.verify_sub_signature("sekret", "p1", "s1", sig) is True
        assert razorpay_subscriptions.verify_sub_signature("sekret", "p1", "s1", "wrong") is False
        assert razorpay_subscriptions.verify_sub_signature("sekret", "p1", "s1", "") is False
        # the one-time order's opposite concatenation must NOT verify here
        flipped = hmac.new(b"sekret", b"s1|p1", hashlib.sha256).hexdigest()
        assert razorpay_subscriptions.verify_sub_signature("sekret", "p1", "s1", flipped) is False


RAZORPAY_LIVE_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_LIVE_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")


@pytest.mark.integration
@pytest.mark.skipif(
    not (RAZORPAY_LIVE_KEY_ID and RAZORPAY_LIVE_KEY_SECRET),
    reason="RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not set — skipped outside a live test-key run",
)
def test_live_create_plan_and_subscription_against_razorpay_sandbox() -> None:
    """Test 5 (key-gated): proves the TEST KEY + request shape really work
    against api.razorpay.com. Never runs in normal CI (no env secrets there)."""
    with httpx.Client(timeout=30.0) as client:
        plan = razorpay_subscriptions.create_plan(
            RAZORPAY_LIVE_KEY_ID, RAZORPAY_LIVE_KEY_SECRET, "CI Pro", 999.0, client=client
        )
        sub = razorpay_subscriptions.create_subscription(
            RAZORPAY_LIVE_KEY_ID,
            RAZORPAY_LIVE_KEY_SECRET,
            plan["plan_id"],
            "ci@tokenops-cost-auditor.com",
            "pro",
            client=client,
        )
    assert plan["currency"] == "INR"
    assert plan["amount"] == 99900
    assert sub["subscription_id"]
