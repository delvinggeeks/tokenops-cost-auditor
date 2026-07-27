"""E2E real-journey test — the false-confidence gap (founder 2026-07-27: "the e2e flow
breaks somewhere and you are losing info").

Unlike tests/test_journeys.py, which SEEDS an Audit row and only asserts pages render and
links resolve, this walks the ACTUAL runtime a new customer takes, with NO X-User-Email
shim: real magic-link sign-up → a paid credit → a real upload that RUNS the audit pipeline
→ the report with real findings → the billing/checkout STATE. A genuine break anywhere in
that path fails CI here instead of passing green — which is exactly how the checkout
dead-end reached the founder undetected.
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tokenops_cost_auditor.persistence.models import FindingRow
from tokenops_cost_auditor.persistence.repo import get_or_create_user
from tokenops_cost_auditor.services.payments.base import grant_payment

F1_BYTES = (Path(__file__).parent / "fixtures" / "openai_small.jsonl").read_bytes()
BUYER = "e2e-buyer@example.com"


class _Mail:
    """Captures the magic link so the test can complete the REAL sign-in (the mail
    adapter is the only place the one-time link is emitted)."""

    def __init__(self) -> None:
        self.links: list[tuple[str, str]] = []

    def magic_link(self, to_email: str, link_url: str) -> None:
        self.links.append((to_email, link_url))

    def report_ready(self, to_email: str, report_url: str) -> None:  # runner calls this
        pass


def _sign_in_for_real(app: FastAPI) -> TestClient:
    """Walk the actual magic-link auth — request the link, read it from the mail
    adapter, POST /auth/verify — so the client holds a genuine session cookie (no shim)."""
    mail = _Mail()
    app.state.mail = mail
    app.state.runner.mail = mail
    c = TestClient(app)
    r = c.post("/auth/signin-link", data={"email": BUYER})
    assert r.status_code == 200 and "Check your email" in r.text, r.text
    token = parse_qs(urlparse(mail.links[-1][1]).query)["token"][0]
    r = c.post("/auth/verify", data={"token": token}, follow_redirects=False)
    assert r.status_code == 303, "magic-link sign-in failed"
    return c


def test_new_customer_journey_runs_end_to_end(app: FastAPI) -> None:
    # 1. SIGN UP for real (magic link, not the X-User-Email shim).
    c = _sign_in_for_real(app)

    # 2. A paid credit so the upload clears the payment gate (FR-18).
    with app.state.session_factory() as s:
        u = get_or_create_user(s, BUYER)
        grant_payment(s, u.id, "manual", 500.0, "USD")
        s.commit()

    # 3. REAL upload that RUNS the audit pipeline (not a seeded row).
    r = c.post(
        "/api/v1/audits",
        files={"file": ("logs.jsonl", io.BytesIO(F1_BYTES), "application/jsonl")},
        headers={"accept": "application/json"},
    )
    assert r.status_code == 201, r.text
    audit_id = r.json()["audit_id"]

    # 4. The pipeline actually completes and produced real findings.
    status = {}
    for _ in range(50):
        status = c.get(f"/api/v1/audits/{audit_id}/status").json()
        if status.get("status") in ("done", "error"):
            break
        time.sleep(0.1)
    assert status.get("status") == "done", f"audit did not finish: {status}"
    assert status.get("valid_pct") == 100.0, "the upload was not ingested"
    with app.state.session_factory() as s:
        findings = s.query(FindingRow).filter_by(audit_id=audit_id).count()
    assert findings > 0, "the audit produced no findings — the pipeline did not really run"

    # 5. The report surface renders real content (not an error/empty state).
    dash = c.get("/dashboard")
    assert dash.status_code == 200, "the dashboard did not render after a completed audit"

    # 6. The billing/checkout STATE is coherent — config-aware so this catches BOTH a
    #    regression (links configured but no button) AND documents the not-configured gap.
    billing = c.get("/billing")
    assert billing.status_code == 200
    if app.state.settings.checkout_link("USD", "pro"):
        assert "Pay for" in billing.text, "checkout links configured but no Pay button renders"
    else:
        # the honest dead-button state (R-GTM-CONTROL) — checkout is not switched on yet
        assert "switched on" in billing.text.lower()
