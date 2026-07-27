"""WebhookPort (R-PLATFORM slice 3, S-5). Outbound `audit.completed` events —
observe-and-notify only, X-01/X-02 SAFE: never in the request path, never
enforces anything on the customer's LLM traffic. `sign` mirrors the INBOUND
verification in api/routes_webhooks.py (razorpay's `verify_signature`) —
raw HMAC-SHA256 hex digest of the exact body bytes — so a receiver's
verification code looks structurally identical to our own inbound checks."""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookPort(Protocol):
    def dispatch_audit_completed(self, workspace_id: str, payload: dict[str, object]) -> None: ...
