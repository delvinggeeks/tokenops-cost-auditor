"""Issue #77 — Stripe Checkout Session for the one-time USD audit.

Verified flow: server creates the Checkout Session FIRST (POST
/v1/checkout/sessions, HTTP Basic Auth secret-key:"", form-encoded body,
unit_amount in cents) -> the browser gets a 303 redirect straight to Stripe's
hosted page -> the EXISTING checkout.session.completed webhook
(services/payments/stripe_link.py, unchanged) is the SOLE credit-grant
authority, idempotent on the Stripe event id -> reflected in the user's state.
"""

from __future__ import annotations

import hashlib
import hmac
import io
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
from tokenops_cost_auditor.persistence.models import Base, Payment
from tokenops_cost_auditor.services.payments import stripe_checkout

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
        database_url=f"sqlite:///{tmp_path / 'stripe.db'}",
        upload_dir=tmp_path / "u",
        report_dir=tmp_path / "r",
        backup_dir=tmp_path / "b",
        stripe_secret_key=STRIPE_SECRET_KEY,
        stripe_webhook_secret=STRIPE_WEBHOOK_SECRET,
        one_shot_usd=500.0,
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


def _fake_session_response(session_id: str = "cs_test_ABC123") -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "id": session_id,
        "url": f"https://checkout.stripe.com/c/pay/{session_id}",
    }
    return resp


def _create_checkout_via_route(client: TestClient, session_id: str = "cs_test_ABC123"):
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.return_value = _fake_session_response(session_id)
    with patch(
        "tokenops_cost_auditor.services.payments.stripe_checkout.httpx.Client",
        return_value=fake_client,
    ):
        resp = client.post("/billing/stripe/checkout", headers=HDR, follow_redirects=False)
    return resp, fake_client


def _webhook_sign(body: bytes, t: int) -> str:
    v1 = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(), f"{t}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return f"t={t},v1={v1}"


def _checkout_completed_event(
    session_id: str, email: str = BUYER, amount_cents: int = 50000, eid: str = "evt_cs_1"
) -> bytes:
    return json.dumps(
        {
            "id": eid,
            "type": "checkout.session.completed",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": session_id,
                    "amount_total": amount_cents,
                    "currency": "usd",
                    "customer_email": email,
                    "payment_status": "paid",
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


def upload(client: TestClient, email: str = BUYER):
    return client.post(
        "/api/v1/audits",
        headers={"X-User-Email": email},
        files={"file": ("logs.jsonl", io.BytesIO(b'{"ts":"2026-07-01T00:00:00Z"}\n'), "x")},
    )


class TestSessionCreate:
    """Test 1: mock the httpx boundary — never hit the network in CI."""

    def test_request_shape_and_redirect(self, sclient: TestClient) -> None:
        resp, fake_client = _create_checkout_via_route(sclient)
        assert resp.status_code == 303, resp.text
        assert resp.headers["location"] == "https://checkout.stripe.com/c/pay/cs_test_ABC123"

        assert fake_client.post.call_count == 1
        args, kwargs = fake_client.post.call_args
        assert args[0] == stripe_checkout.CHECKOUT_URL
        assert kwargs["auth"] == (STRIPE_SECRET_KEY, "")  # Basic Auth, sk_ as username
        payload = kwargs["data"]
        assert payload["mode"] == "payment"
        assert payload["line_items[0][price_data][currency]"] == "usd"
        assert payload["line_items[0][price_data][unit_amount]"] == "50000"  # USD 500 -> cents
        assert payload["line_items[0][price_data][product_data][name]"] == "One-time audit"
        assert payload["line_items[0][quantity]"] == "1"
        assert payload["customer_email"] == BUYER
        assert payload["metadata[user_email]"] == BUYER
        assert payload["metadata[purpose]"] == "one_shot_audit"
        assert payload["success_url"].startswith(
            "https://tokenops-cost-auditor.com/billing?checkout=success&session_id="
        )
        assert "{CHECKOUT_SESSION_ID}" in payload["success_url"]
        assert (
            payload["cancel_url"] == "https://tokenops-cost-auditor.com/billing?checkout=cancelled"
        )

    def test_accepts_restricted_key(self, tmp_path: Path) -> None:
        # rk_test_... — preferred per Stripe's current best-practice, used
        # IDENTICALLY as sk_ in Basic Auth (no `sk_` assumption anywhere).
        app = create_app(_settings(tmp_path, stripe_secret_key="rk_test_restricted"))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        resp, fake_client = _create_checkout_via_route(client)
        assert resp.status_code == 303
        _, kwargs = fake_client.post.call_args
        assert kwargs["auth"] == ("rk_test_restricted", "")
        app.state.engine.dispose()

    def test_session_create_error_surfaces_502(self, sclient: TestClient) -> None:
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.post.return_value = MagicMock(status_code=401, json=lambda: {})
        with patch(
            "tokenops_cost_auditor.services.payments.stripe_checkout.httpx.Client",
            return_value=fake_client,
        ):
            resp = sclient.post("/billing/stripe/checkout", headers=HDR, follow_redirects=False)
        assert resp.status_code == 502


class TestFullJourney:
    """Test 2: create-session -> signed checkout.session.completed webhook
    (payment_status=paid) -> credit granted BY THE WEBHOOK -> reflected in the
    user's state. A bad Stripe-Signature grants nothing."""

    def test_journey_grants_via_webhook_and_unlocks_upload(
        self, sclient: TestClient, sapp: FastAPI
    ) -> None:
        assert upload(sclient).status_code == 402  # before payment: blocked

        resp, _ = _create_checkout_via_route(sclient, session_id="cs_journey1")
        assert resp.status_code == 303
        with sapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None  # not yet — webhook grants it

        webhook_resp = _post_webhook(
            sclient, _checkout_completed_event("cs_journey1", eid="evt_journey1")
        )
        assert webhook_resp.status_code == 200
        assert webhook_resp.json() == {"status": "processed"}
        with sapp.state.session_factory() as session:
            payment = session.scalar(select(Payment))
            assert payment is not None
            assert payment.provider == "stripe" and payment.ref == "cs_journey1"
            assert payment.amount == 500.0 and payment.currency == "USD"

        assert upload(sclient).status_code == 201  # reflected in the user's state

    def test_bad_signature_400_and_grants_nothing(self, sclient: TestClient, sapp: FastAPI) -> None:
        body = _checkout_completed_event("cs_bad1", eid="evt_bad1")
        resp = sclient.post(
            "/api/v1/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )
        assert resp.status_code == 400
        with sapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None


class TestIdempotency:
    """Test 3: a re-delivered checkout.session.completed (same event id)
    grants the credit exactly once."""

    def test_redelivered_event_grants_once(self, sclient: TestClient, sapp: FastAPI) -> None:
        body = _checkout_completed_event("cs_dup1", eid="evt_dup_shared")
        first = _post_webhook(sclient, body)
        second = _post_webhook(sclient, body)  # re-delivered, same event id
        assert first.json() == {"status": "processed"}
        assert second.json() == {"status": "duplicate"}
        with sapp.state.session_factory() as session:
            payments = list(session.scalars(select(Payment).where(Payment.ref == "cs_dup1")))
        assert len(payments) == 1


class TestHonestState:
    """Test 4: key unset -> disabled 'not switched on'; cancel_url -> honest
    cancelled state; success_url -> honest processing state that grants
    nothing by itself (the webhook is the sole authority)."""

    def test_billing_page_shows_disabled_note_without_key(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, stripe_secret_key=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        page = client.get("/billing?ccy=USD", headers=HDR)
        assert page.status_code == 200
        assert "Checkout opens once billing is switched on." in page.text
        app.state.engine.dispose()

    def test_billing_page_shows_button_when_configured(self, sclient: TestClient) -> None:
        page = sclient.get("/billing?ccy=USD", headers=HDR)
        assert page.status_code == 200
        assert 'action="/billing/stripe/checkout"' in page.text
        assert "Buy one-time audit" in page.text

    def test_checkout_create_disabled_without_key(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, stripe_secret_key=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        resp = client.post("/billing/stripe/checkout", headers=HDR, follow_redirects=False)
        assert resp.status_code == 503
        app.state.engine.dispose()

    def test_cancel_redirect_shows_honest_cancelled_state(self, sclient: TestClient) -> None:
        page = sclient.get("/billing?ccy=USD&checkout=cancelled", headers=HDR)
        assert page.status_code == 200
        assert "Checkout cancelled — nothing was charged." in page.text

    def test_success_redirect_shows_honest_processing_state_and_grants_nothing(
        self, sclient: TestClient, sapp: FastAPI
    ) -> None:
        page = sclient.get(
            "/billing?ccy=USD&checkout=success&session_id=cs_test_ABC123", headers=HDR
        )
        assert page.status_code == 200
        assert "Payment received" in page.text
        with sapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None  # landing here never grants


class TestCheckoutModuleUnit:
    """create_session exercised directly (no FastAPI) — the injected-client
    path and the missing-id/url response shape."""

    def test_create_session_with_injected_client(self) -> None:
        fake = MagicMock()
        fake.post.return_value = _fake_session_response("cs_direct1")
        session = stripe_checkout.create_session(
            STRIPE_SECRET_KEY,
            199.5,
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
        assert kwargs["data"]["line_items[0][price_data][unit_amount]"] == "19950"

    def test_response_missing_id_or_url_raises(self) -> None:
        fake = MagicMock()
        fake.post.return_value = MagicMock(status_code=200, json=lambda: {"id": "cs_x"})
        with pytest.raises(stripe_checkout.CheckoutCreateError):
            stripe_checkout.create_session(
                STRIPE_SECRET_KEY,
                1.0,
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
def test_live_create_session_against_stripe() -> None:
    """Test 5 (key-gated): proves the TEST key + request shape really work
    against api.stripe.com. Never runs in normal CI (no env secret there)."""
    with httpx.Client(timeout=30.0) as client:
        session = stripe_checkout.create_session(
            STRIPE_LIVE_SECRET_KEY,
            1.0,
            success_url="https://tokenops-cost-auditor.com/billing?checkout=success",
            cancel_url="https://tokenops-cost-auditor.com/billing?checkout=cancelled",
            email="ci@tokenops-cost-auditor.com",
            client=client,
        )
    assert session["id"].startswith("cs_")
    assert session["url"].startswith("https://checkout.stripe.com/")
