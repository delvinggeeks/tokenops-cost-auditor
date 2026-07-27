"""Issue #74 — Razorpay Standard Checkout for the one-time INR audit.

Verified flow: server creates the order first (POST /v1/orders, Basic Auth,
amount in paise) -> client opens checkout.js against that order_id -> the
modal's signed callback is checked server-side for UX only (B1) -> the
`order.paid` / `payment.captured` webhook is the SOLE credit-grant authority,
idempotent on `order_id` (B3) -> `payment.failed` is an honest no-credit
state (B4).
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
from tokenops_cost_auditor.services.payments import razorpay_orders

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
        database_url=f"sqlite:///{tmp_path / 'rzp.db'}",
        upload_dir=tmp_path / "u",
        report_dir=tmp_path / "r",
        backup_dir=tmp_path / "b",
        razorpay_key_id=RZP_KEY_ID,
        razorpay_key_secret=RZP_KEY_SECRET,
        razorpay_webhook_secret=RZP_WEBHOOK_SECRET,
        one_shot_inr=20000.0,
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


def _fake_order_response(order_id: str = "order_ABC123") -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": order_id}
    return resp


def _create_order_via_route(client: TestClient, order_id: str = "order_ABC123") -> dict:
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.post.return_value = _fake_order_response(order_id)
    with patch(
        "tokenops_cost_auditor.services.payments.razorpay_orders.httpx.Client",
        return_value=fake_client,
    ):
        resp = client.post("/billing/razorpay/order", headers=HDR)
    return resp, fake_client  # type: ignore[return-value]


def _handler_sign(order_id: str, payment_id: str) -> str:
    # Independent fixture computation (R-PAY convention): the provider formula,
    # not the adapter code under test.
    return hmac.new(
        RZP_KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


def _webhook_sign(body: bytes) -> str:
    return hmac.new(RZP_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _order_paid_event(
    order_id: str, email: str = BUYER, amount_paise: int = 2000000, eid: str = "evt_order_1"
) -> bytes:
    return json.dumps(
        {
            "event": "order.paid",
            "event_id": eid,
            "created_at": int(time.time()),
            "payload": {
                "order": {
                    "entity": {
                        "id": order_id,
                        "amount": amount_paise,
                        "currency": "INR",
                        "notes": {"email": email},
                        "status": "paid",
                    }
                },
                "payment": {
                    "entity": {
                        "id": "pay_" + eid,
                        "order_id": order_id,
                        "amount": amount_paise,
                        "currency": "INR",
                        "status": "captured",
                    }
                },
            },
        }
    ).encode()


def _payment_captured_event(
    order_id: str, email: str = BUYER, amount_paise: int = 2000000, eid: str = "evt_cap_1"
) -> bytes:
    return json.dumps(
        {
            "event": "payment.captured",
            "event_id": eid,
            "created_at": int(time.time()),
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_" + eid,
                        "order_id": order_id,
                        "amount": amount_paise,
                        "currency": "INR",
                        "notes": {"email": email},
                        "status": "captured",
                    }
                }
            },
        }
    ).encode()


def _payment_failed_event(order_id: str, email: str = BUYER, eid: str = "evt_fail_1") -> bytes:
    return json.dumps(
        {
            "event": "payment.failed",
            "event_id": eid,
            "created_at": int(time.time()),
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_" + eid,
                        "order_id": order_id,
                        "amount": 2000000,
                        "currency": "INR",
                        "notes": {"email": email},
                        "status": "failed",
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


def upload(client: TestClient, email: str = BUYER):
    return client.post(
        "/api/v1/audits",
        headers={"X-User-Email": email},
        files={"file": ("logs.jsonl", io.BytesIO(b'{"ts":"2026-07-01T00:00:00Z"}\n'), "x")},
    )


class TestOrderCreate:
    """Test 1: mock the httpx boundary — never hit the network in CI."""

    def test_request_shape_and_response(self, rclient: TestClient) -> None:
        resp, fake_client = _create_order_via_route(rclient)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["order_id"] == "order_ABC123"
        assert body["currency"] == "INR"
        assert body["key_id"] == RZP_KEY_ID

        assert fake_client.post.call_count == 1
        args, kwargs = fake_client.post.call_args
        assert args[0] == razorpay_orders.ORDERS_URL
        assert kwargs["auth"] == (RZP_KEY_ID, RZP_KEY_SECRET)  # Basic Auth
        payload = kwargs["json"]
        assert payload["currency"] == "INR"
        assert payload["amount"] == 2000000  # INR 20,000 -> paise
        assert payload["notes"]["email"] == BUYER

    def test_order_create_error_surfaces_502(self, rclient: TestClient) -> None:
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.post.return_value = MagicMock(status_code=401, json=lambda: {})
        with patch(
            "tokenops_cost_auditor.services.payments.razorpay_orders.httpx.Client",
            return_value=fake_client,
        ):
            resp = rclient.post("/billing/razorpay/order", headers=HDR)
        assert resp.status_code == 502


class TestSignatureVerify:
    """Test 2: real HMAC, valid vs tampered — the handler endpoint is
    signature-check-only (UX per B1); it never itself grants the credit."""

    def test_valid_signature_verified(self, rclient: TestClient, rapp: FastAPI) -> None:
        order_id, payment_id = "order_valid1", "pay_valid1"
        sig = _handler_sign(order_id, payment_id)
        resp = rclient.post(
            "/billing/razorpay/verify",
            headers=HDR,
            data={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "verified"}
        # B1: a valid handler signature is UX-only — no credit yet.
        with rapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None

    def test_tampered_signature_400(self, rclient: TestClient, rapp: FastAPI) -> None:
        order_id, payment_id = "order_bad1", "pay_bad1"
        resp = rclient.post(
            "/billing/razorpay/verify",
            headers=HDR,
            data={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": "deadbeef",
            },
        )
        assert resp.status_code == 400
        with rapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None

    def test_verify_disabled_without_secret(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, razorpay_key_secret=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        resp = client.post(
            "/billing/razorpay/verify",
            headers=HDR,
            data={"razorpay_order_id": "o", "razorpay_payment_id": "p", "razorpay_signature": "s"},
        )
        assert resp.status_code == 503
        app.state.engine.dispose()


class TestFullJourney:
    """Test 3: create-order -> handler-POST (200, UX) -> signed order.paid
    webhook (THE grant, per B1) -> reflected in the user's state (upload
    unlocks). A tampered handler signature grants nothing."""

    def test_journey_grants_via_webhook_and_unlocks_upload(
        self, rclient: TestClient, rapp: FastAPI
    ) -> None:
        assert upload(rclient).status_code == 402  # before payment: blocked

        resp, _ = _create_order_via_route(rclient, order_id="order_journey1")
        order_id = resp.json()["order_id"]

        sig = _handler_sign(order_id, "pay_journey1")
        verify_resp = rclient.post(
            "/billing/razorpay/verify",
            headers=HDR,
            data={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_journey1",
                "razorpay_signature": sig,
            },
        )
        assert verify_resp.status_code == 200 and verify_resp.json()["status"] == "verified"
        with rapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None  # not yet — webhook grants it

        webhook_resp = _post_webhook(rclient, _order_paid_event(order_id))
        assert webhook_resp.status_code == 200 and webhook_resp.json()["status"] == "processed"
        with rapp.state.session_factory() as session:
            payment = session.scalar(select(Payment))
            assert payment is not None
            assert payment.provider == "razorpay" and payment.ref == order_id
            assert payment.amount == 20000.0 and payment.currency == "INR"

        assert upload(rclient).status_code == 201  # reflected in the user's state

    def test_tampered_handler_signature_400_and_grants_nothing(
        self, rclient: TestClient, rapp: FastAPI
    ) -> None:
        resp, _ = _create_order_via_route(rclient, order_id="order_tamper1")
        order_id = resp.json()["order_id"]
        bad_resp = rclient.post(
            "/billing/razorpay/verify",
            headers=HDR,
            data={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_tamper1",
                "razorpay_signature": "not-the-real-signature",
            },
        )
        assert bad_resp.status_code == 400
        with rapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None


class TestIdempotency:
    """Test 4 (B3): the credit is granted exactly once when both the handler
    path and a re-delivered order.paid webhook arrive for the same order_id;
    payment.captured firing for an order already credited by order.paid is
    also a no-op. payment.failed grants nothing (B4 honest failure)."""

    def test_handler_plus_redelivered_webhook_grants_once(
        self, rclient: TestClient, rapp: FastAPI
    ) -> None:
        order_id = "order_dup1"
        sig = _handler_sign(order_id, "pay_dup1")
        rclient.post(
            "/billing/razorpay/verify",
            headers=HDR,
            data={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_dup1",
                "razorpay_signature": sig,
            },
        )
        body = _order_paid_event(order_id, eid="evt_dup_shared")
        first = _post_webhook(rclient, body)
        second = _post_webhook(rclient, body)  # re-delivered, same event id
        assert first.json() == {"status": "processed"}
        assert second.json() == {"status": "duplicate"}
        with rapp.state.session_factory() as session:
            payments = list(session.scalars(select(Payment).where(Payment.ref == order_id)))
        assert len(payments) == 1

    def test_order_paid_and_payment_captured_collapse_to_one_credit(
        self, rclient: TestClient, rapp: FastAPI
    ) -> None:
        order_id = "order_dup2"
        paid = _post_webhook(rclient, _order_paid_event(order_id, eid="evt_paid_2"))
        captured = _post_webhook(rclient, _payment_captured_event(order_id, eid="evt_captured_2"))
        assert paid.json() == {"status": "processed"}
        # different event_id, SAME order_id — order_id-keyed dedup catches it
        assert captured.json() == {"status": "processed"}
        with rapp.state.session_factory() as session:
            payments = list(session.scalars(select(Payment).where(Payment.ref == order_id)))
        assert len(payments) == 1

    def test_payment_failed_grants_nothing(self, rclient: TestClient, rapp: FastAPI) -> None:
        order_id = "order_failed1"
        resp = _post_webhook(rclient, _payment_failed_event(order_id))
        assert resp.status_code == 200 and resp.json() == {"status": "processed"}
        with rapp.state.session_factory() as session:
            assert session.scalar(select(Payment)) is None
        assert upload(rclient, "nocredit@company.com").status_code == 402


class TestHonestState:
    """Test 5: key/secret unset -> disabled 'not switched on', never a
    broken modal or a wrong-currency button."""

    def test_billing_page_shows_disabled_note_without_keys(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, razorpay_key_id="", razorpay_key_secret=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        page = client.get("/billing?ccy=INR", headers=HDR)
        assert page.status_code == 200
        assert "Checkout opens once billing is switched on." in page.text
        assert 'id="rzp-oneshot-btn"' not in page.text
        app.state.engine.dispose()

    def test_billing_page_shows_button_when_configured(self, rclient: TestClient) -> None:
        page = rclient.get("/billing?ccy=INR", headers=HDR)
        assert page.status_code == 200
        assert 'id="rzp-oneshot-btn"' in page.text
        assert "checkout.razorpay.com" in page.text
        assert "Content-Security-Policy" in page.headers
        assert "https://checkout.razorpay.com" in page.headers["Content-Security-Policy"]
        assert "https://api.razorpay.com" in page.headers["Content-Security-Policy"]

    def test_order_create_disabled_without_keys(self, tmp_path: Path) -> None:
        app = create_app(_settings(tmp_path, razorpay_key_id="", razorpay_key_secret=""))
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        resp = client.post("/billing/razorpay/order", headers=HDR)
        assert resp.status_code == 503
        app.state.engine.dispose()


class TestOrdersModuleUnit:
    """create_order/verify_order_signature exercised directly (no FastAPI)."""

    def test_create_order_with_injected_client(self) -> None:
        fake = MagicMock()
        fake.post.return_value = _fake_order_response("order_direct1")
        order = razorpay_orders.create_order(
            RZP_KEY_ID, RZP_KEY_SECRET, 199.5, receipt="r1", email="a@b.com", client=fake
        )
        assert order == {"order_id": "order_direct1", "amount": 19950, "currency": "INR"}
        _, kwargs = fake.post.call_args
        assert kwargs["auth"] == (RZP_KEY_ID, RZP_KEY_SECRET)

    def test_verify_order_signature_real_hmac(self) -> None:
        sig = hmac.new(b"sekret", b"o1|p1", hashlib.sha256).hexdigest()
        assert razorpay_orders.verify_order_signature("sekret", "o1", "p1", sig) is True
        assert razorpay_orders.verify_order_signature("sekret", "o1", "p1", "wrong") is False
        assert razorpay_orders.verify_order_signature("sekret", "o1", "p1", "") is False


RAZORPAY_LIVE_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_LIVE_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")


@pytest.mark.integration
@pytest.mark.skipif(
    not (RAZORPAY_LIVE_KEY_ID and RAZORPAY_LIVE_KEY_SECRET),
    reason="RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not set — skipped outside a live test-key run",
)
def test_live_create_order_against_razorpay_sandbox() -> None:
    """Test 6 (key-gated): proves the TEST KEY + request shape really work
    against api.razorpay.com. Never runs in normal CI (no env secrets there)."""
    with httpx.Client(timeout=30.0) as client:
        order = razorpay_orders.create_order(
            RAZORPAY_LIVE_KEY_ID,
            RAZORPAY_LIVE_KEY_SECRET,
            1.0,
            receipt="ci-live-check",
            email="ci@tokenops-cost-auditor.com",
            client=client,
        )
    assert order["currency"] == "INR"
    assert order["amount"] == 100
    assert order["order_id"]
