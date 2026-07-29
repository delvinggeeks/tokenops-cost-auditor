# CODE-TOUR.md — a guided reading of this codebase

For a technical founder who did not write it (WP-COMPREHEND). Read in this
order — it follows the money: an uploaded log file's journey from upload to
purge, then the systems around it. Each stop: what it does, the requirement
it serves, the ONE function to read first, and the test that proves it.

Terms are defined the first time they appear. Times are ~15 min per stop.

---

## Part 1 — the audit pipeline (the product)

### Stop 1: `src/tokenops_cost_auditor/api/routes_upload.py` — the front door

Receives the customer's log file over HTTP, checks they're signed in and have
an unconsumed audit credit (the free first audit grants one, so the mechanism
is identical for free and paid), saves the file to disk, and creates an
"audit" row in the database with status `queued`. Nothing is analyzed here —
it only accepts and records.
- Serves: FR-01 (upload), FR-18 (payment gate), FR-26 (safe retries).
- Read first: `create_audit()` — follow it top to bottom; every guard
  (session, credit, size, idempotency) is one `if` block.
- Proof: `tests/test_api.py`.
- Terms: an **idempotency key** is a client-chosen label letting a retry of
  the same upload return the same audit instead of charging twice. A
  **session** here means the signed browser cookie identifying a logged-in
  user.

### Stop 2: `src/tokenops_cost_auditor/services/ingest/` — making rows uniform

Turns three possible file formats (OpenAI JSONL, Anthropic JSONL, generic
CSV) into ONE uniform table of calls: timestamp, model, and four token
counts per row. Prompt text is thrown away at this door — only counts and an
optional fingerprint (hash) survive.
- Serves: FR-01/02/03 (parse, preserve metadata, count bad rows), FR-22 (no
  text stored).
- Read first: `load()` in `ingest/__init__.py` (9 lines — the whole stage),
  then `normalize()` in `normalizer.py`.
- Proof: `tests/test_ingest.py`.
- Terms: **JSONL** = a text file with one JSON object per line. A
  **prefix hash** is a short fingerprint (SHA-256) of a prompt's first 4,096
  characters — it proves two prompts started identically without keeping the
  text. A **frame** is the in-memory table (pandas DataFrame) all later
  stages share.

### Stop 3: `src/tokenops_cost_auditor/services/pricing/` — what each call cost

Looks up each call's model in the price file
(`src/tokenops_cost_auditor/services/pricing/data/prices.yaml`) and
computes its dollar cost from the four token counts. Models not in the file
are listed as "unpriced" and excluded — never guessed. Since R-AUTO-PRICING
(2026-07-23) the price file is agent-verified, not hand-verified: every
current rate row must be corroborated exactly by an independent
machine-readable source or the release fails — `scripts/pricing_verify.py`
is that strict gate (CI step + pre-deploy).
- Serves: FR-05/06 (pricing), NFR-07 (totals reconcile within ±0.5%),
  NFR-15 (price file freshness).
- Read first: `apply()` in `coster.py`, then `rate()` in `table.py` (the
  date-aware lookup).
- Proof: `tests/test_pricing.py` — 15 hand-computed rows the code must match
  exactly.
- Terms: **effective-dated** means each price row carries a start date and a
  call is priced at the rate valid on its own day. **Cache read/write
  rates**: providers charge less to re-serve a stored prompt prefix (read)
  and slightly more to store it (write).

### Stop 4: `src/tokenops_cost_auditor/services/rules/` — the nine detectors

Nine independent modules each scan the priced frame for one waste pattern
and emit "findings" with a conservative dollar estimate. The ids run d1–d6
and d8–d10 — the id d7 was never shipped, so "d1..d10" in older design notes
is span notation, not a count. d1–d6 are the original six (FR-07..FR-12,
one per detector); d8 spend-concentration and d9 ineffective-cache landed
with the richer-findings ruling (founder 2026-07-25); d10 spend-anomaly is
FR-33. Three of the nine (d8/d9/d10) need per-request data — route tags,
cache-write counts, a daily series — so they stay silent on coarse
provider-aggregate sources rather than guessing. `registry.py` runs them in
order; `findings.py` holds the shared building blocks (severity thresholds,
evidence sampling, the as-billed token rate); `detector_copy.py` carries the
plain-English copy each finding shows.
- Serves: FR-07..FR-12 (one per original detector), FR-13 (ranked findings),
  FR-33 (spend anomaly).
- Read first: `findings.py::effective_prompt_rate()` (10 lines — the pricing
  honesty rule every estimate uses), then any one detector's `run()`;
  `d4_retry_storm.py` is the shortest.
- Proof: `tests/test_rules.py` — every detector pinned to a hand-derived
  dollar figure (see `tests/fixtures/pricing_golden_NOTES.md` for the
  arithmetic) plus a clean-traffic fixture that must produce ZERO findings.
- Terms: a **golden test** pins output to a known-correct value computed
  independently (spreadsheet first, code second). **Evidence rows** are up
  to 20 sample calls per finding — counts and timestamps only.

### Stop 5: `src/tokenops_cost_auditor/services/runner.py` — the conductor

The one function that runs a whole audit: load → price → detect → aggregate →
render → email, updating the audit row's status (`queued` → `processing` →
`done`/`failed`) as it goes. Also enforces the "only 2 audits at once" cap.
- Serves: NFR-10/13 (background processing, concurrency cap), FR-19 re-runs.
- Read first: `AuditRunner.run()` — it IS the pipeline, one call per stage.
- Proof: `tests/test_runner.py` (end-to-end on the waste-pack fixture).
- Terms: **BackgroundTasks** = FastAPI's way to keep working after the HTTP
  response is sent — no separate job queue in v1.

### Stop 6: `src/tokenops_cost_auditor/services/report/` — one truth, three outputs

`model.py` assembles every number ONCE into a ReportModel (including the
headline savings, capped at spend); `render_json.py`, the web page, and
`render_pdf.py` only display it. The PDF and web page share one HTML
template, so they can never disagree.
- Serves: FR-14/15/28/30 (report content, signed links, pricing provenance,
  API-equivalent framing), T-REP-01 (no renderer recomputes).
- Read first: `ReportModel.build()` — every displayed number is born here.
- Proof: `tests/test_report_web.py` and `tests/test_runner.py` (byte-identical
  JSON on re-run).
- Terms: a **signed URL** embeds a tamper-proof, expiring token in the link
  itself, so reports need no password. **WeasyPrint** renders our HTML into
  the PDF server-side.

### Stop 7: `src/tokenops_cost_auditor/services/lifecycle/` — keeping the promise

`purge.py` deletes raw uploads 7 days after the report (daily scheduled job);
`auditlog.py` appends every privileged action to a log table that has no
update or delete code path at all.
- Serves: FR-21 (auto-purge), FR-20 (actions logged), FR-23 (the public
  7-day promise).
- Read first: `purge_due()` — 15 lines, including the failed-audit fallback.
- Proof: `tests/test_lifecycle.py`.
- Terms: **append-only** = rows can be added, never changed; the database
  role loses UPDATE/DELETE rights on that table at deploy.

## Part 2 — the systems around the pipeline

### Stop 8: `src/tokenops_cost_auditor/web/auth.py` + `routes_auth.py` — sign-in

Passwordless: you email a signed link that logs you in once and then dies.
Consuming a link records the login moment; any link issued at-or-before that
moment is dead — that's the whole single-use mechanism, no token table.
(Machine access — SDK keys, API tokens, OAuth apps — is separate: Stop 13.)
- Serves: FR-17. Read first: `verify_magic_token()`. Proof: `tests/test_auth.py`.

### Stop 9: `src/tokenops_cost_auditor/services/payments/` + `web/routes_billing.py`

Three plans — free, pro, team — all defined in `plans.py`, the single source
of every money amount the product renders. Two ways to pay, both real
Standard Checkout (the 2026-07-27 pivot away from hosted payment links):
one-time purchases (Razorpay Orders, Stripe Checkout Sessions) grant audit
credits; subscriptions (`razorpay_subscriptions.py`, `stripe_subscriptions.py`)
grant a plan, and `subscriptions.py::entitlements()` is the one answer to
"what may this account do". Card data never touches us — the provider's
checkout collects it. A credit is still consumed atomically at upload (two
simultaneous uploads cannot spend one credit — the database update itself is
the lock). Webhooks in `api/routes_webhooks.py` are verified with ~30 lines
of standard-library HMAC, time-boxed, and deduplicated in an append-only
table.
- Serves: FR-18/27. Read first: `claim_credit()` in `payments/base.py` (the
  atomic heart), then `entitlements()`.
- Proof: `tests/test_payments.py` (credits, webhooks) plus the four checkout
  suites — `tests/test_razorpay_checkout.py`, `tests/test_razorpay_subscriptions.py`,
  `tests/test_stripe_checkout.py`, `tests/test_stripe_subscriptions.py` — and
  `tests/test_subscriptions.py` (entitlements).
- Terms: a **webhook** is the payment provider calling OUR server to say
  "someone paid". **HMAC** is a keyed checksum proving the call really came
  from the provider. An **entitlement** is a computed answer ("2 sources,
  weekly audits") derived from the live subscription, never stored copy.

### Stop 10: `src/tokenops_cost_auditor/web/routes_admin.py` — your panel

Token-gated (wrong token sees 404, not a login page): list audits, re-run,
purge, mark-paid, download PDF. Every action lands in the audit log with the
caller's IP.
- Serves: FR-19/20. Read first: `admin_actor()` (the gate). Proof:
  `tests/test_payments.py` (TestTADM classes).

### Stop 11: `src/tokenops_cost_auditor/persistence/` — the database layer

`models.py` defines the 31 tables (grown from the original 8 as the
platform track landed — workspaces, tokens, subscriptions, statements,
events); `repo.py` holds the small helpers routes call instead of touching
the database directly; `migrations/` holds the numbered schema-change
scripts, a chain of 24 (001→024) at this writing (a **migration** = a
versioned script that alters tables; ours only ever ADD, never drop, so
rollback is just running older code).
- Serves: NFR-11 (UTC everywhere). Read first: `models.py` top to bottom —
  it is the data dictionary. Proof: every test exercises it.
- Terms: the **session factory** is the function handing out short-lived
  database connections; one per request or job, closed after.

### Stop 12: `docker-compose.yml` + `scripts/` — the machine it runs on

Four containers: **Caddy** (the reverse proxy — the public doorman that
holds the TLS certificate and forwards traffic to the app), the app,
Postgres (never exposed publicly), and **ofelia** (the cron sidecar — a tiny
scheduler container that runs the timed jobs inside the others). `scripts/`
holds the ops tools: backup, daily digest, pricing verify/refresh, monthly
statements, the OpenAPI exporter, the loop driver.
- Serves: NFR-08/09 (backups, 30-min deploy). Read first: docker-compose.yml
  itself with `docs/06-OPS-RUNBOOK.md` §1 beside it.
- Proof: the D10 restore drill log (runbook §4) and `tests/test_ops_scripts.py`.

### Stop 13: the platform API — three doors, all read-or-ingest, none a proxy

The API-first surface (R-PLATFORM). Door one, WRITE: the Python SDK in
`src/tokenops_cost_auditor/sdk/` (`init()` auto-instruments every OpenAI and
Anthropic call the customer's process makes — counts, model, timing; prompt
text is never read, FR-22 by construction) and the JS SDK in `sdk/js/`, both
posting to `POST /api/v1/ingest` in `web/routes_ingest.py` (its own bearer
key kind, rate-limited, idempotent). Door two, READ: `web/routes_api_read.py`
serves audits/findings/breakdown behind scoped API tokens minted on the
`/developer` page (`web/routes_developer.py`); `web/api_auth.py` resolves the
bearer, `web/api_scopes.py` enforces scope subsets. Door three, THIRD-PARTY:
`web/routes_oauth.py` is a full OAuth 2.0 authorization server
(authorization-code + PKCE, read scopes only, redirect URIs matched
byte-exact), and `src/tokenops_cost_auditor/mcp/server.py` exposes the same
read surface as MCP tools. None of the three can touch, gate, or proxy the
customer's LLM traffic — X-01/X-02 hold everywhere.
- Serves: R-PLATFORM / R-SDK-PLATFORM (S-1 SDK, S-6 OAuth), FR-22.
- Read first: `resolve_read_bearer()` in `web/api_auth.py` (one function =
  the whole read-auth model), then `ingest()` in `routes_ingest.py`.
- Proof: `tests/test_sdk.py`, `tests/test_ingest_api.py`,
  `tests/test_developer_platform.py` (tokens, scopes AND the OAuth server —
  PKCE, redirect byte-match), `tests/test_mcp.py`.
- Terms: a **bearer token** is a secret string presented in the
  Authorization header; whoever bears it, may. A **scope** is a named slice
  of permission ("read:audits") a token is limited to. **PKCE** is the OAuth
  extension proving the app that finishes a login is the one that started
  it. **MCP** (Model Context Protocol) lets an AI assistant call our read
  API as tools.

### Stop 14: `src/tokenops_cost_auditor/web/authz.py` + `routes_members.py` — orgs

R-ORG: a **workspace** is the entity that owns resources (audits, sources,
statements); every user is a workspace of one by default, orgs are opt-in.
Four roles — owner, admin, member, viewer — and a `Perm` enum; `can(role,
perm)` is the entire authorization matrix, `ensure()` raises the honest 403.
Roles gate PRODUCT actions only (who may mint keys, see billing, invite
members) — never the customer's LLM traffic (X-01/X-02). Invites and role
changes live in `routes_members.py`. The audit engine stays tenant-blind:
`services/rules/` and `services/pricing/` never learn what a workspace is —
tenancy is applied at the web/persistence boundary.
- Serves: R-ORG (O-0..O-2), FR-20 (role changes audit-logged).
- Read first: `can()` in `authz.py` — the whole matrix in one screen.
- Proof: `tests/test_authz.py`, `tests/test_workspace_members.py`,
  `tests/test_rbac_journey.py` (a full invite→role→403 walk).
- Terms: **RBAC** = role-based access control — permissions attach to roles,
  roles attach to members.

### Stop 15: `src/tokenops_cost_auditor/services/flywheel/` — learning without text

The intelligence lifecycle (docs/12), built to learn from outcomes while
FR-22 stays absolute. `frame.py::extract()` turns finding verdicts the
customer recorded (applied / dismissed — the **L0 labels**) into
TrainingRows keyed by a **pseudonym** (an HKDF-derived opaque id — a one-way
keyed hash, so rows correlate without naming anyone). `cohort.py::status()`
reports where we stand on the L1–L4 learning ladder and refuses to climb
before its n-thresholds — no learning on n=1. `benchmarks.py` computes peer
comparisons; `export.py::build()` is the FR-35 cohort export: explicit
workspace opt-in, aggregate-only features, and a k≥10 floor that refuses
below-floor exports by naming n and the floor rather than blurring. The
flywheel reads the engine's OUTPUTS only — it never imports the engine
(R-F4, pinned by test).
- Serves: FR-34..FR-38 span (FR-35 shipped), docs/12 intent law, FR-22.
- Read first: `frame.py::extract()`, then `export.py::build()`.
- Proof: `tests/test_flywheel.py`, `tests/test_cohort_export.py` (pinned
  envelope golden, below-floor refusal, pseudonym-space disjointness).
- Terms: **HKDF** derives purpose-bound keys from one secret, so frame and
  export pseudonyms can never be joined. The **k-floor** (k-anonymity)
  means a figure is published only when at least k workspaces stand behind
  it.

### Stop 16: `src/tokenops_cost_auditor/services/statements/` — the owner artifact

One page a month for whoever signs off on the bill and never logs in: plain
text, one column, the number leads. The money math lives in ONE place —
`services/dashboard/savings.py::compute()`: a saving is **verified** only
when a finding the customer marked applied is re-measured by a later audit
covering ≥7 days (delta capped at the original estimate); otherwise it stays
pending or identified — never a fabricated figure (R-Q9). `build.py` renders
the statement from that summary with provenance stamps for every audit;
`archive()` freezes a statement once sent; `web/routes_statements.py` serves
the archive and `scripts/monthly_statements.py` is the cron entry.
- Serves: R-Q9 (verified-only headline), FR-30 (equiv-spend line), FR-37
  residue tracked in QUEUE (per-finding provenance lines).
- Read first: `savings.py::compute()` — the one formula; then
  `statements/build.py::build()`.
- Proof: `tests/test_verified_savings.py` (goldens, derivation in the NOTES
  sheet), `tests/test_statements.py` (arithmetic, labelling, frozen-once-sent).

---

Done? The acceptance bar (PLAN §0.1 WP-COMPREHEND): trace any report finding
to its detector and test, and explain Stops 1-7 aloud, plainly, in under
five minutes. Stops 13-16 are the platform track — read them before touching
anything under `web/` or `services/flywheel/`.
