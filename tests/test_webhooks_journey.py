"""R-PLATFORM slice 3 (S-5), Issue #56 — outbound webhooks journey.

Add endpoint -> run a real audit -> a signed best-effort delivery is
attempted with the correct FR-22-clean payload (no text) -> the UI shows it.
RBAC: a non-manager never sees the add/remove controls and a forged POST
fails closed (403). Signature: computed INDEPENDENTLY of the dispatcher code
(test_payments.py convention) and must verify with the shown-once secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from test_runner import TEXT_MARKERS, seed_audit
from tokenops_cost_auditor.persistence.models import (
    WebhookDelivery,
    WebhookEndpoint,
    WorkspaceMember,
)
from tokenops_cost_auditor.persistence.repo import (
    get_or_create_user,
    get_or_create_workspace,
    set_active_workspace,
)

OWNER = "wh-owner@example.com"
MEMBER = "wh-member@example.com"


def _hdr(email: str) -> dict[str, str]:
    return {"X-User-Email": email}


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _add_member(app: FastAPI, owner_email: str, member_email: str) -> str:
    """Seeds `owner_email` as owner and `member_email` as a member of the SAME
    workspace (the test_rbac_journey.py pattern). Returns the workspace id."""
    with app.state.session_factory() as s:
        owner = get_or_create_user(s, owner_email)
        ws = get_or_create_workspace(s, owner)
        member = get_or_create_user(s, member_email)
        s.add(WorkspaceMember(workspace_id=ws.id, user_id=member.id, role="member"))
        s.flush()
        set_active_workspace(s, member.id, ws.id)
        s.commit()
        return ws.id


class TestWebhookJourney:
    def test_add_run_deliver_and_ui_shows_it(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = TestClient(app)
        client.get("/dashboard", headers=_hdr(OWNER))  # creates the owner + workspace

        captured: dict[str, object] = {}

        def fake_post(
            url: str, *, content: bytes, headers: dict[str, str], timeout: float
        ) -> _FakeResponse:
            captured["url"] = url
            captured["body"] = content
            captured["headers"] = headers
            return _FakeResponse(200)

        monkeypatch.setattr(httpx, "post", fake_post)

        add = client.post(
            "/settings/webhooks", data={"url": "https://example.com/hook"}, headers=_hdr(OWNER)
        )
        assert add.status_code == 200
        match = re.search(r"<code>(whsec_[^<]+)</code>", add.text)
        assert match is not None, "signing secret not shown on creation"
        secret = match.group(1)

        audit_id = seed_audit(app, "waste_pack_anthropic.jsonl", email=OWNER)
        app.state.runner.run(audit_id)

        assert captured.get("url") == "https://example.com/hook"
        body_bytes = captured["body"]
        assert isinstance(body_bytes, bytes)
        payload = json.loads(body_bytes)
        assert payload["event"] == "audit.completed"
        assert payload["audit_id"] == audit_id
        assert payload["status"] == "done"
        assert payload["finding_count"] == len(payload["findings"])
        for f in payload["findings"]:
            assert set(f) == {"detector", "severity", "monthly_usd"}

        # FR-22: never a prompt/completion marker anywhere in the wire body
        body_text = body_bytes.decode()
        for marker in TEXT_MARKERS:
            assert marker not in body_text

        # signature verifies INDEPENDENTLY with the secret shown at creation
        headers = captured["headers"]
        assert isinstance(headers, dict)
        expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, headers["X-TokenOps-Signature"])
        assert headers["X-TokenOps-Event"] == "audit.completed"

        with app.state.session_factory() as s:
            deliveries = list(s.scalars(select(WebhookDelivery)))
        assert len(deliveries) == 1
        assert deliveries[0].status_code == 200
        assert deliveries[0].event == "audit.completed"

        page = client.get("/settings/webhooks", headers=_hdr(OWNER)).text
        assert "https://example.com/hook" in page
        assert "200 ok" in page

    def test_delivery_failure_is_recorded_and_never_raises(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Best-effort by construction: a dead endpoint records a null status
        and must never fail the audit it reports on."""
        client = TestClient(app)
        client.get("/dashboard", headers=_hdr(OWNER))
        client.post(
            "/settings/webhooks", data={"url": "https://dead.example/hook"}, headers=_hdr(OWNER)
        )

        def raising_post(url: str, **kwargs: object) -> _FakeResponse:
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", raising_post)

        audit_id = seed_audit(app, "waste_pack_anthropic.jsonl", email=OWNER)
        app.state.runner.run(audit_id)  # must not raise

        from tokenops_cost_auditor.persistence.models import Audit

        with app.state.session_factory() as s:
            audit = s.get(Audit, audit_id)
            assert audit is not None and audit.status == "done"
            deliveries = list(s.scalars(select(WebhookDelivery)))
        assert len(deliveries) == 1
        assert deliveries[0].status_code is None


class TestWebhookRBAC:
    def test_non_manager_does_not_see_the_controls(self, app: FastAPI) -> None:
        _add_member(app, OWNER, MEMBER)
        client = TestClient(app)
        owner_page = client.get("/settings/webhooks", headers=_hdr(OWNER)).text
        assert 'name="url"' in owner_page

        member_page = client.get("/settings/webhooks", headers=_hdr(MEMBER)).text
        assert 'name="url"' not in member_page
        assert "managed by owners and admins" in member_page.lower()

    def test_non_manager_add_fails_closed(self, app: FastAPI) -> None:
        _add_member(app, OWNER, MEMBER)
        client = TestClient(app)
        r = client.post(
            "/settings/webhooks",
            data={"url": "https://example.com/hook"},
            headers=_hdr(MEMBER),
            follow_redirects=False,
        )
        assert r.status_code == 403
        with app.state.session_factory() as s:
            assert list(s.scalars(select(WebhookEndpoint))) == []

    def test_non_manager_delete_fails_closed(self, app: FastAPI) -> None:
        ws_id = _add_member(app, OWNER, MEMBER)
        client = TestClient(app)
        client.post(
            "/settings/webhooks", data={"url": "https://example.com/hook"}, headers=_hdr(OWNER)
        )
        with app.state.session_factory() as s:
            endpoint = s.scalar(
                select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == ws_id)
            )
            assert endpoint is not None
            endpoint_id = endpoint.id
        r = client.post(
            f"/settings/webhooks/{endpoint_id}/delete",
            headers=_hdr(MEMBER),
            follow_redirects=False,
        )
        assert r.status_code == 403
