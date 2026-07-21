# API overview

The JSON API lives under `/api/v1/`. Web pages (landing, upload, reports,
admin) are session-driven HTML and are not part of the versioned API surface.
<!-- src: FR-25 -->

## Authentication

Sign-in is a magic link: you post your email, receive a single-use link that
expires in 15 minutes, and get a session cookie (`HttpOnly`, `Secure`,
`SameSite=Lax`). Consuming a link invalidates it and every earlier link for
that account. API calls authenticate with the session cookie. The admin panel
is separate, gated by an `X-Admin-Token` header, and returns 404 — not 401 —
when the token is absent or wrong. <!-- src: FR-17; HLD §6 -->

## Payment gate

One payment buys one audit credit; one upload consumes one credit atomically.
Uploading without an unconsumed credit returns `402` with payment links in the
response. Webhooks from the payment providers are HMAC-verified, checked
against a 5-minute timestamp tolerance, and deduplicated in an append-only
event table — a replayed webhook event can never grant a second credit.
<!-- src: FR-18; FR-27 -->

## Idempotency

`POST /api/v1/audits` honors the `Idempotency-Key` header: the first request
returns `201`, an identical retry returns `200` with the same audit — safe to
retry on network failure without double-charging your credit.
<!-- src: FR-26 -->

## Rate limits and queueing

Upload and auth endpoints are rate-limited per authenticated user where a
session exists, per IP otherwise; `429` responses carry `Retry-After`.
Current limits: `POST /api/v1/audits` 10/minute; magic-link and
early-access endpoints 5/minute. Processing has a concurrency cap: audits
beyond it hold in `queued` status and the status endpoint reports your
queue position. <!-- src: NFR-03/12/13; routes_upload/@limiter -->

## Machine-readable spec

The live OpenAPI document is served at `/openapi.json` on the application
domain — generated from the running API, so it cannot drift from the
deployment.
Interactive API explorers and issued API keys arrive together (that surface
is trigger-registered: the first customer request for programmatic access).
<!-- src: FR-25; BACKLOG R-APIKEYS -->

## Upload constraints

Files up to 200 MB; accepted formats are OpenAI JSONL, Anthropic JSONL, and
the [generic CSV contract](../quickstart.md#option-upload-a-log-file). Format
detection is per file; a file that parses as none of the three is rejected
with a message telling you exactly what was expected. <!-- src: FR-01 -->

## Signed report URLs

Report links are signed and expire after 30 days. Tampered or expired tokens
return 404 with no information about whether the audit exists.
<!-- src: FR-15 -->

## Errors

Every `/api/v1` error uses one envelope: <!-- src: NFR-14 -->

```json
{
  "error": {
    "code": "payment_required",
    "message": "This audit requires payment before processing.",
    "request_id": "6d3f2c..."
  }
}
```

| HTTP | `code` |
|---|---|
| 400 | `bad_request` |
| 401 | `unauthorized` |
| 402 | `payment_required` |
| 404 | `not_found` |
| 413 | `payload_too_large` |
| 422 | `validation_error` |
| 429 | `rate_limited` |
| 500 | `internal_error` |

`request_id` matches the server logs — include it when contacting support.
Error messages are user-safe by policy: parsing errors tell you what the
parser expected, never echo your data back. <!-- src: docs/03 §8 -->

The full endpoint list is [generated from the code](endpoints.md) on every CI
run.
