# API reference

Send your LLM usage to TokenOps Cost Auditor and it runs the full
six-detector audit — priced, dollar-ranked, and reachable in your dashboard.
This is the curated, example-driven reference; the
[machine-generated endpoint list](endpoints.md) mirrors the live OpenAPI
schema exactly.

- **Base URL** — `https://tokenops-cost-auditor.com/api/v1`
  Self-hosted? Swap the host; every path below is identical.
- **Versioning** — the JSON API is versioned in the path (`/api/v1`). Web
  pages (landing, upload, reports, admin) are session-driven HTML and are
  **not** part of the versioned surface.
- **One promise on every path** — we accept and store token **counts**,
  timestamps, and model names. Prompt or completion **text is rejected at
  the door** (see [The counts-only contract](#the-counts-only-contract)).

---

## Authentication

Programmatic calls authenticate with an **ingest key**. Mint one under
**Sources → SDK &amp; API → Mint an ingest key** (Pro and Team plans). It is
shown once and stored hashed; revoking it deletes our copy immediately.

The key is delivered as a **DSN** — one string carrying the endpoint and the
key — for drop-in configuration:

```
TOKENOPS_COST_AUDITOR_DSN=https://ik_9f2Xw7…@tokenops-cost-auditor.com
```

On the wire, the key is a bearer token:

```
Authorization: Bearer ik_9f2Xw7…
```

An ingest key is **write-only** by construction: it can send usage and read
nothing, so a leaked key can never expose your data — only pollute it, which
you see in the runs ledger and revoke in one click.

---

## Send usage

`POST /api/v1/ingest`

Submit a batch of per-call usage records. They enter the same pipeline as an
uploaded log — full six-detector coverage — and a report lands in your
dashboard. Idempotent: safe to retry.

### Request body

```json
{
  "records": [
    {
      "ts": "2026-07-24T10:00:00Z",
      "provider": "openai",
      "model": "gpt-5.4",
      "prompt_tokens": 3084,
      "completion_tokens": 47,
      "cached_tokens": 0
    }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `ts` | string | ✅ | ISO-8601 (UTC assumed if naive) |
| `provider` | string | ✅ | `openai`, `anthropic`, or any lowercase label used for pricing |
| `model` | string | ✅ | model id as billed |
| `prompt_tokens` | integer | ✅ | total input tokens (cached portion included) |
| `completion_tokens` | integer | ✅ | output tokens |
| `cached_tokens` | integer | | cache-read subset of input |
| `cache_write_tokens` | integer | | cache-creation input tokens |
| `latency_ms` | number | | round-trip latency |
| `endpoint` | string | | e.g. `openai.chat.completions` |
| `request_id` | string | | your correlation id |
| `tag` | string | | free label — service, team, agent session |
| `declared_max_tokens` | integer | | the `max_tokens` you set |
| `prefix_hash` | string | | SHA-256 hex over the first 4096 prompt chars, computed **client-side** — enables the cache and duplicate detectors without any text leaving your process |

Up to **5,000 records** per batch. Send an `Idempotency-Key` header to make
retries safe. Every token/count integer must fall in the range
`0`–`1,000,000,000,000`; a value outside it (or of the wrong type) is rejected
with a `422` naming the field.

### Examples

=== "curl"

    ```bash
    curl -X POST https://tokenops-cost-auditor.com/api/v1/ingest \
      -H "Authorization: Bearer $TOKENOPS_COST_AUDITOR_KEY" \
      -H "Content-Type: application/json" \
      -H "Idempotency-Key: batch-2026-07-24-a" \
      -d '{
        "records": [
          {"ts":"2026-07-24T10:00:00Z","provider":"openai","model":"gpt-5.4",
           "prompt_tokens":3084,"completion_tokens":47,"cached_tokens":0}
        ]
      }'
    ```

=== "Python (requests)"

    ```python
    import os, requests

    resp = requests.post(
        "https://tokenops-cost-auditor.com/api/v1/ingest",
        headers={
            "Authorization": f"Bearer {os.environ['TOKENOPS_COST_AUDITOR_KEY']}",
            "Idempotency-Key": "batch-2026-07-24-a",
        },
        json={"records": [
            {"ts": "2026-07-24T10:00:00Z", "provider": "openai", "model": "gpt-5.4",
             "prompt_tokens": 3084, "completion_tokens": 47, "cached_tokens": 0},
        ]},
        timeout=30,
    )
    print(resp.json())   # {"audit_id": "...", "records": 1, "replayed": False}
    ```

=== "Python (SDK)"

    ```python
    # pip install tokenops-cost-auditor
    import tokenops_cost_auditor.sdk as toca
    toca.init()   # reads TOKENOPS_COST_AUDITOR_DSN from the environment

    # every OpenAI & Anthropic call is now captured automatically —
    # token counts only, never your prompts. See "Python SDK" below.
    ```

=== "TypeScript"

    ```typescript
    const resp = await fetch("https://tokenops-cost-auditor.com/api/v1/ingest", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.TOKENOPS_COST_AUDITOR_KEY}`,
        "Content-Type": "application/json",
        "Idempotency-Key": "batch-2026-07-24-a",
      },
      body: JSON.stringify({
        records: [{
          ts: "2026-07-24T10:00:00Z", provider: "openai", model: "gpt-5.4",
          prompt_tokens: 3084, completion_tokens: 47, cached_tokens: 0,
        }],
      }),
    });
    console.log(await resp.json());
    ```

=== "Go"

    ```go
    body := `{"records":[{"ts":"2026-07-24T10:00:00Z","provider":"openai",
      "model":"gpt-5.4","prompt_tokens":3084,"completion_tokens":47,"cached_tokens":0}]}`
    req, _ := http.NewRequest("POST",
        "https://tokenops-cost-auditor.com/api/v1/ingest", strings.NewReader(body))
    req.Header.Set("Authorization", "Bearer "+os.Getenv("TOKENOPS_COST_AUDITOR_KEY"))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Idempotency-Key", "batch-2026-07-24-a")
    resp, err := http.DefaultClient.Do(req)
    ```

### Responses

| Status | Body | Meaning |
|---|---|---|
| `201` | `{"audit_id":"…","records":N,"replayed":false}` | accepted; the audit is running |
| `200` | `{"audit_id":"…","replayed":true}` | this `Idempotency-Key` was already processed |
| `401` | [error envelope](#errors) | missing or revoked ingest key |
| `402` | error envelope | subscription lapsed — ingest pauses until it resumes |
| `413` | error envelope | batch exceeds 5,000 records |
| `422` | error envelope | a record broke the counts-only contract, is missing a required field, carries an out-of-range or wrong-typed value, or the body isn't a non-empty `records` array — the message names the offender |
| `429` | error envelope | rate limit exceeded |

---

## Run an audit (upload)

`POST /api/v1/audits`

The paid, one-shot twin of [Send usage](#send-usage): upload a whole export
file and it runs the full six-detector audit once, instead of streaming
records as your process makes calls. This is the same endpoint the
dashboard's upload page calls.

**Auth is different here** — not the ingest key. It authenticates with your
**signed-in session cookie** (magic-link sign-in), because it's the API
twin of a browser action, not a headless-integration path. If you're
scripting outside a browser, [Send usage](#send-usage) (the ingest key)
is almost always the right endpoint instead.

Two gates apply before the file is even read:

- **Payment gate (FR-18)** — an unconsumed paid credit must exist on your
  account, or you get a `402` back with payment links; the credit is
  claimed atomically the moment the audit is created (never double-spent by
  two concurrent uploads).
- **Role gate** — running an audit spends a run, which every role except
  **viewer** may do. A viewer gets a `403`.

### Request

`multipart/form-data` with one field:

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | ✅ | one of `.jsonl`, `.json`, `.csv` — the same three formats the [quickstart](../quickstart.md#option-upload-a-log-file) documents |

Up to **200 MB**. Send an `Idempotency-Key` header to make retries safe —
identical to [Send usage](#send-usage)'s idempotency contract.

=== "curl"

    ```bash
    curl -X POST https://tokenops-cost-auditor.com/api/v1/audits \
      -H "Cookie: session=$TOKENOPS_COST_AUDITOR_SESSION" \
      -H "Idempotency-Key: audit-2026-07-24-a" \
      -F "file=@usage_export.jsonl"
    ```

=== "Python (requests)"

    ```python
    import os, requests

    resp = requests.post(
        "https://tokenops-cost-auditor.com/api/v1/audits",
        cookies={"session": os.environ["TOKENOPS_COST_AUDITOR_SESSION"]},
        headers={"Idempotency-Key": "audit-2026-07-24-a"},
        files={"file": open("usage_export.jsonl", "rb")},
        timeout=60,
    )
    print(resp.json())   # {"audit_id": "...", "replayed": False}
    ```

### Responses

| Status | Body | Meaning |
|---|---|---|
| `201` | `{"audit_id":"…","replayed":false}` | accepted; the audit is queued/running |
| `200` | `{"audit_id":"…","replayed":true}` | this `Idempotency-Key` was already processed |
| `400` | [error envelope](#errors) | unsupported file extension, or the file is empty/unparseable |
| `401` | error envelope | no valid session |
| `402` | error envelope | no unconsumed paid credit — the body includes payment links |
| `403` | error envelope | a viewer role tried to run an audit |
| `413` | error envelope | file exceeds the 200MB upload limit |
| `429` | error envelope | rate limit exceeded (10/minute) |

A signed-in browser (`Accept: text/html`) is redirected to the progress page
instead of receiving JSON — the API contract above applies to every other
client.

---

## Check audit status

`GET /api/v1/audits/{audit_id}/status`

Poll an audit created by an upload. Authenticated by your **session** (this
is a dashboard-side endpoint), not the ingest key.

```json
{ "audit_id": "…", "status": "queued", "queue_position": 3 }
```

`status` is one of `queued`, `processing`, `done`, `failed`. **Code to the
presence of each key, not to a fixed shape** — the body grows as the audit
advances:

- `valid_pct` (0–100) appears once validation has run; it is **absent while
  the audit is still `queued`**.
- `queue_position` is present **only** while `queued`.
- `error` is present **only** on a `failed` audit.

Ingest-created audits also appear in your dashboard's **Runs** ledger the
moment they land.

---

## Retrieve a report

Reports are served behind a **signed, expiring URL** — the token *is* the
authorization, so these carry no auth header and are safe to forward to
someone who never logs in.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/r/{token}` | the report as HTML |
| `GET` | `/r/{token}/pdf` | the report as a PDF |

The link is emailed when a report is ready and expires after 30 days.

---

## Read your data

The ingest key writes; to **read** your audits and findings back out, use a
**read token** or an **OAuth access token**. Both are read-only and both carry
**scopes** — a token can do only what its scopes allow.

Mint a personal read token under **Developer → API tokens**, tick the scopes it
needs, and send it as a bearer token:

```
Authorization: Bearer rt_7Qx…
```

Two read scopes exist today (there is deliberately **no** write scope — writing
stays the ingest key's job):

| Scope | Grants |
|---|---|
| `read:audits` | list your audits — status, spend totals, counts |
| `read:findings` | read the findings inside an audit — detector, severity, dollar impact |

### List audits

`GET /api/v1/audits` · scope `read:audits`

Returns your most recent audits (newest first; `?limit=` up to 200). Counts and
dollars only.

=== "curl"

    ```bash
    curl -H "Authorization: Bearer $TOKENOPS_COST_AUDITOR_TOKEN" \
      https://tokenops-cost-auditor.com/api/v1/audits
    ```

=== "Python"

    ```python
    import os, requests
    r = requests.get(
        "https://tokenops-cost-auditor.com/api/v1/audits",
        headers={"Authorization": f"Bearer {os.environ['TOKENOPS_COST_AUDITOR_TOKEN']}"},
        timeout=30,
    )
    for a in r.json()["audits"]:
        print(a["id"], a["status"], a["total_spend_usd"], a["findings"])
    ```

```json
{
  "audits": [
    {
      "id": "…", "status": "done", "created_at": "2026-07-24T10:00:00Z",
      "records": 1200, "observed_days": 7, "total_spend_usd": 42.5,
      "projected_spend_usd": 170.0, "savings_pct": 18.0,
      "equiv_spend": false, "findings": 3
    }
  ]
}
```

### Get an audit's summary

`GET /api/v1/audits/{audit_id}` · scope `read:audits`

Returns one audit's own summary — totals, cost, counts, scope, and timing. An
audit that isn't yours is a `404` (never a `403`), same as findings below. An
audit that hasn't finished yet returns its honest partial totals with
`status` reflecting that (never a `500`).

```json
{
  "id": "…", "status": "done", "scope_label": "anthropic",
  "created_at": "2026-07-24T10:00:00Z", "completed_at": "2026-07-24T10:02:00Z",
  "totals": {
    "calls": 1200, "input_tokens": 900000, "output_tokens": 300000,
    "total_tokens": 1200000, "estimated_cost_usd": 42.5
  },
  "model_count": 3, "finding_count": 3
}
```

### List findings

`GET /api/v1/audits/{audit_id}/findings` · scope `read:findings`

Returns the audit's findings, ranked by monthly impact. An audit that isn't
yours is a `404` (never a `403`), so a token can't probe which audit ids exist.

```json
{
  "audit_id": "…",
  "findings": [
    {
      "id": "d1-001", "detector": "d1_model_overkill", "route": "gpt-5.4",
      "severity": "high", "confidence": "ESTIMATED",
      "monthly_cost_impact_usd": 31.0, "fix": "Route these calls to a cheaper model."
    }
  ]
}
```

A token with `read:audits` but not `read:findings` gets a `403`
(`forbidden`) here — scopes are enforced per endpoint.

---

## OAuth applications

To let **someone else's** app read a customer's data — the standard "Authorize"
button — register an OAuth application under **Developer → OAuth applications**.
You get a `client_id` and a `client_secret` (shown once). The flow is the
**authorization-code grant with PKCE** (RFC 6749 + RFC 7636), read scopes only.

**1. Send the user to authorize** (`code_challenge` is the S256 hash of a
per-request `code_verifier` you keep):

```
GET https://tokenops-cost-auditor.com/oauth/authorize
  ?response_type=code
  &client_id=oac_…
  &redirect_uri=<one of your registered URIs, matched byte-for-byte>
  &scope=read:audits+read:findings
  &state=<random, echoed back>
  &code_challenge=<base64url(sha256(verifier))>
  &code_challenge_method=S256
```

The user sees a consent screen listing the scopes and approves. We redirect to
your `redirect_uri` with `?code=…&state=…`. (An unknown `client_id` or an
unregistered `redirect_uri` is shown an error on our site and is **never**
redirected — the open-redirect guard.)

**2. Exchange the code** for a read-only access token:

```bash
curl -X POST https://tokenops-cost-auditor.com/oauth/token \
  -d grant_type=authorization_code \
  -d code=oaq_… \
  -d redirect_uri=<the same URI> \
  -d client_id=oac_… \
  -d client_secret=oas_… \
  -d code_verifier=<the original verifier>
```

```json
{ "access_token": "at_…", "token_type": "Bearer", "expires_in": 2592000, "scope": "read:audits" }
```

The authorization code is **single-use** and expires in 5 minutes. Use the
`at_…` token exactly like a read token on the endpoints above. Token-endpoint
errors follow RFC 6749 (`{"error": "invalid_grant"}`, `invalid_client`, …), not
the envelope below. Revoking the app deletes its secret **and** stops every
access token it ever issued.

---

## Python SDK

```python
# pip install tokenops-cost-auditor
import tokenops_cost_auditor.sdk as toca
toca.init()   # reads TOKENOPS_COST_AUDITOR_DSN from the environment
```

After `init()`, every OpenAI and Anthropic call your process makes is
captured — token counts, model, and timing — and sent to your account. Three
guarantees:

- **Counts only, by construction.** The SDK reads only the response's `usage`
  and `model`. It never touches `choices`/`content`/`messages`, so a prompt
  cannot be serialized. Proven in the SDK's own test suite.
- **Observe-only.** It never sits in your request path. Your real call runs
  first and returns unmodified; recording is a best-effort side effect that
  cannot break, slow, or alter the call. A dead network drops records
  silently — never a retry storm in your process.
- **Inert without a DSN.** No `TOKENOPS_COST_AUDITOR_DSN` set = the SDK does
  nothing, exactly like Sentry.

Optional labeling — `environment` and `tag` both fold into the **single**
`tag` field the counts-only contract carries (truncated to 120 characters).
If you pass both, `tag` wins and `environment` is dropped — pass one:

```python
toca.init(tag="checkout-service")   # or: toca.init(environment="prod")
```

---

## The counts-only contract

Every ingestion path — the API, the SDK, uploads — accepts **token counts,
timestamps, and model names only**. This is not a policy you can opt out of;
it is enforced at the door. A record carrying a `prompt`, `messages`,
`content`, or any field outside the schema above is **rejected with `422`,
naming the offending field**, rather than silently dropped:

```json
{
  "error": {
    "code": "validation_error",
    "message": "records[0] carries fields outside the counts-only contract: messages, prompt. We never accept prompt or completion content (FR-22) — send token counts; precompute prefix_hash client-side if you want cache detection.",
    "request_id": "…"
  }
}
```

We refuse the data we promise never to hold — so an integration can never
teach itself that sending text is acceptable.

---

## Idempotency

Send an `Idempotency-Key` header on any `POST`. The first request is
processed and the key recorded; a replay with the same key returns the
original result (`200`, `"replayed": true`) instead of creating a second
audit. Use a stable key per batch (a hash of the batch contents works well —
the SDK does exactly this).

---

## Rate limits

`POST /api/v1/ingest` is limited **per ingest key** (a busy key never starves
another) with a **per-source-IP ceiling** on top (the abuse bound). Well
above a single busy integration's needs; a `429` returns the
[error envelope](#errors) — back off and retry.

---

## Errors

Every `/api/v1` error returns one uniform envelope (`/healthz` and web pages
excepted):

```json
{
  "error": {
    "code": "unauthorized",
    "message": "unknown or revoked ingest key",
    "request_id": "a1b2c3d4e5f6"
  }
}
```

Quote the `request_id` when you contact support; it ties your error to our
logs. Quick reference, then the full catalog below:

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | malformed request |
| 401 | `unauthorized` | missing/revoked key |
| 402 | `payment_required` | no active subscription/credit |
| 403 | `forbidden` | a valid token that lacks the required read scope |
| 404 | `not_found` | unknown resource |
| 413 | `payload_too_large` | batch/file too big |
| 422 | `validation_error` | the counts-only contract was broken |
| 429 | `rate_limited` | slow down |
| 500 | `internal_error` | our side — the `request_id` is your reference |

### Error catalog — trigger and fix

#### 400 `bad_request`

**Triggers:** [Run an audit](#run-an-audit-upload)'s `file` has an
unsupported extension (only `.jsonl`, `.json`, `.csv` are accepted), or the
file is empty/unparseable as any of the three formats.
**Fix:** check the extension and that the file has at least one row/record;
the message names exactly what was expected.

#### 401 `unauthorized`

**Triggers:** [Send usage](#send-usage) got no `Authorization` header, a
header that isn't `Bearer ik_…`, or an ingest key that's unknown/revoked;
[Run an audit](#run-an-audit-upload) and [Check audit status](#check-audit-status)
got no valid session cookie; [Read your data](#read-your-data) got no
`Authorization: Bearer rt_…`/`at_…` or an unknown/revoked/expired one.
**Fix:** mint a fresh key/token — see [Authentication](#authentication) —
and confirm you're sending the exact `Bearer <prefix>_…` scheme for the
endpoint you're calling; the three credential kinds (`ik_`, `rt_`, `at_`)
are not interchangeable.

#### 402 `payment_required`

**Triggers:** [Send usage](#send-usage) — your subscription lapsed, so
ingest pauses until it resumes; [Run an audit](#run-an-audit-upload) — no
unconsumed paid credit exists yet.
**Fix:** the response body carries the payment link(s) (Stripe/Razorpay) —
pay, then retry the exact same request; an `Idempotency-Key` makes that
retry safe.

#### 403 `forbidden`

**Triggers:** two distinct causes, both fail-closed. (1) [Read your
data](#read-your-data) — a valid read/OAuth token that's missing the
specific scope the endpoint needs (`read:audits` or `read:findings`); a
token can do only what its scopes list. (2) [Run an audit](#run-an-audit-upload) —
a **viewer** role tried to spend a run; every other role may.
**Fix:** for (1), mint a token with the missing scope under **Developer →
API tokens**; for (2), have an owner/admin/member run the audit instead — a
viewer's role can't be escalated by retrying.

#### 404 `not_found`

**Triggers:** an audit id that doesn't exist **or** belongs to a different
account/workspace — both return the identical `404`, never a `403`, so a
token can't use the error to probe which ids exist; a tampered, expired, or
already-consumed report link ([Retrieve a report](#retrieve-a-report)).
**Fix:** double-check the id came from your own [List audits](#list-audits)
response; for report links, request a fresh one — links expire after 30 days
and cannot be renewed by editing the token.

#### 413 `payload_too_large`

**Triggers:** [Send usage](#send-usage) — a batch over 5,000 records;
[Run an audit](#run-an-audit-upload) — a file over 200MB.
**Fix:** split the batch/file (per-week slices work well for large log
exports) and send multiple requests/audits instead of one oversized one.

#### 422 `validation_error`

**Triggers:** [Send usage](#send-usage) only — a record carries a field
outside the counts-only contract (`prompt`, `messages`, `content`, …), is
missing/empty on a required field, or has a value outside the documented
type/range (see [the field table](#send-usage) and
[the counts-only contract](#the-counts-only-contract)).
**Fix:** the message names the offending record index and field —
fix that field; never retry unmodified, since the same record will fail
again identically.

#### 429 `rate_limited`

**Triggers:** you're over a limit — see [Rate limits](#rate-limits)
(`POST /api/v1/ingest` 60/minute per key plus a per-IP abuse ceiling;
`POST /api/v1/audits` 10/minute).
**Fix:** back off and retry; the response carries a `Retry-After` header —
wait at least that long before your next attempt.

#### 500 `internal_error`

**Triggers:** a failure on our side, not yours.
**Fix:** retry once; if it persists, contact support with the `request_id`
from the envelope — it's your reference into our logs.

---

## Webhooks

Inbound webhooks (`/api/v1/webhooks/stripe`, `/api/v1/webhooks/razorpay`) are
how our payment providers notify us of a completed payment. They are
HMAC-verified, timestamp-checked, and deduplicated — a replayed event can
never grant a second credit. They are not something you call.
