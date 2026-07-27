# Webhooks

Get a signed HTTP notification the moment an audit completes — wire TokenOps
into CI, Slack, or your own systems. Observe-and-notify only: webhooks never
sit in your LLM request path and never enforce anything on your traffic.

## Register an endpoint

Under **Settings → Webhooks**, add your URL (owner/admin only — see
[RBAC](reference.md#authentication)). The signing secret is shown **once**:

```
whsec_7Qx…
```

Store it somewhere safe — we keep our own copy to sign every delivery, but we
never show it to you again.

## What we send

When an audit finishes, we POST an `audit.completed` event to every active
endpoint in your workspace:

```json
{
  "event": "audit.completed",
  "audit_id": "a1b2c3d4",
  "workspace_id": "w9f8e7d6",
  "status": "done",
  "total_spend_usd": 1284.55,
  "projected_spend_usd": 940.10,
  "savings_pct": 26.8,
  "finding_count": 4,
  "findings": [
    {"detector": "d1_oversized_model", "severity": "high", "monthly_usd": 210.40},
    {"detector": "d2_missing_cache", "severity": "medium", "monthly_usd": 88.15}
  ]
}
```

That's the whole payload — counts, dollars, and finding metadata only. There
is **never** a prompt, a completion, or any other request text in this or any
TokenOps payload (FR-22); we don't store that text ourselves, so there is
nothing to leak.

## Verify the signature

Every request carries two headers:

| Header | Value |
|---|---|
| `X-TokenOps-Signature` | HMAC-SHA256 of the exact request body, hex-encoded, keyed with your endpoint's signing secret |
| `X-TokenOps-Event` | The event name, e.g. `audit.completed` |

Recompute the digest over the raw body bytes and compare it with
[`hmac.compare_digest`](https://docs.python.org/3/library/hmac.html#hmac.compare_digest)
— never `==`, which leaks timing information:

```python
import hashlib
import hmac

def verify(secret: str, body: bytes, signature_header: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)

# inside your webhook handler, BEFORE parsing the body as JSON:
# if not verify(WEBHOOK_SECRET, request.body, request.headers["X-TokenOps-Signature"]):
#     return 400
```

This is the exact scheme our own inbound payment webhooks verify with — a
receiver's code looks structurally identical to ours.

## Delivery is best-effort

Each completed audit gets **one delivery attempt per active endpoint**, with a
short timeout. A failed or slow delivery is recorded (visible on the
Webhooks page) but never retried automatically, and never delays or blocks
the audit it reports on — a durable retry queue is a future improvement, not
today's guarantee. Design your handler to be idempotent on `audit_id` if that
matters to you.

## Remove an endpoint

Removing a webhook on the Settings page stops deliveries immediately and
deletes our copy of the signing secret — the row stays only so past delivery
history remains visible.
