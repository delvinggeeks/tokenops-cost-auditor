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
paid, saves the file to disk, and creates an "audit" row in the database with
status `queued`. Nothing is analyzed here — it only accepts and records.
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

Looks up each call's model in an agent-verified price file
(`data/prices.yaml`) and computes its dollar cost from the four token
counts. Models not in the file are listed as "unpriced" and excluded —
never guessed. "Agent-verified" (R-AUTO-PRICING) means every CURRENT rate
row is checked by `scripts/pricing_verify.py` against an independent
machine-readable feed on every release — there is no founder hand-check
step; a mismatch or an uncovered row fails the run.
- Serves: FR-05/06 (pricing), NFR-07 (totals reconcile within ±0.5%),
  NFR-15 (price file freshness — now the last successful AGENT
  verification, not a human's).
- Read first: `apply()` in `coster.py`, then `rate()` in `table.py` (the
  date-aware lookup); for the verification gate itself, `scripts/
  pricing_verify.py`'s module docstring names the source ladder.
- Proof: `tests/test_pricing.py` — 15 hand-computed rows the code must match
  exactly — plus `tests/test_pricing_verify.py` for the verification gate.
- Terms: **effective-dated** means each price row carries a start date and a
  call is priced at the rate valid on its own day. **Cache read/write
  rates**: providers charge less to re-serve a stored prompt prefix (read)
  and slightly more to store it (write).

### Stop 4: `src/tokenops_cost_auditor/services/rules/` — the nine detectors

Nine independent modules (`d1_...` through `d10_...`, skipping `d7` — that
id was never shipped) each scan the priced frame for one waste pattern and
emit "findings" with a conservative dollar estimate. `registry.py` runs
them in registry order (`DETECTORS`); `findings.py` holds the shared
building blocks (severity thresholds, evidence sampling, the as-billed token
rate).
- Serves: FR-07..FR-12 (the original six), plus the d8-d10 additions
  (spend concentration, ineffective cache, spend anomaly), FR-13 (ranked
  findings).
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
- Serves: FR-17. Read first: `verify_magic_token()`. Proof: `tests/test_auth.py`.

### Stop 9: `src/tokenops_cost_auditor/services/payments/` + `api/routes_webhooks.py`

Two money paths, not one. The **one-shot audit** is Razorpay Standard
Checkout (`razorpay_orders.py`) or a Stripe Checkout Session
(`stripe_checkout.py`): a provider order/session is created server-side,
the customer pays on the provider's page, and one completed payment = one
audit credit — consumed atomically at upload (two simultaneous uploads
cannot spend one credit — the database update itself is the lock). The
**recurring plan** (`razorpay_subscriptions.py`, `stripe_subscriptions.py`)
sells the `free`/`pro`/`team` catalogue in `payments/plans.py` — the ONE
place every price and entitlement is named, never inlined. Both paths
fulfil only on a verified webhook (never on a success-page redirect, which
a user can reach without paying); webhooks from Razorpay/Stripe are
verified with ~30 lines of standard-library HMAC, time-boxed, and
deduplicated in an append-only table.
- Serves: FR-18/27. Read first: `claim_credit()` in `payments/base.py` for
  the one-shot credit ledger, then `plans.py`'s `Plan` dataclass for the
  subscription catalogue.
- Proof: `tests/test_payments.py`, `tests/test_razorpay_checkout.py`,
  `tests/test_stripe_checkout.py`.
- Terms: a **webhook** is the payment provider calling OUR server to say
  "someone paid". **HMAC** is a keyed checksum proving the call really came
  from the provider. **Standard Checkout** is Razorpay's order-then-modal
  flow (`POST /razorpay/order` creates the order; the client opens the
  `checkout.js` modal against it).

### Stop 10: `src/tokenops_cost_auditor/web/routes_admin.py` — your panel

Token-gated (wrong token sees 404, not a login page): list audits, re-run,
purge, mark-paid, download PDF. Every action lands in the audit log with the
caller's IP.
- Serves: FR-19/20. Read first: `admin_actor()` (the gate). Proof:
  `tests/test_payments.py` (TestTADM classes).

### Stop 11: `src/tokenops_cost_auditor/persistence/` — the database layer

`models.py` defines the 31 tables (the original audit pipeline plus every
platform-era addition — workspaces, sources, saved views, the developer
platform, cohort/flywheel, statements); `repo.py` holds the small helpers
routes call instead of touching the database directly; `migrations/` holds
the numbered schema-change scripts, chained 001 through 024 (a
**migration** = a versioned script that alters tables; ours only ever ADD,
never drop, so rollback is just running older code).
- Serves: NFR-11 (UTC everywhere). Read first: `models.py` top to bottom —
  it is the data dictionary. Proof: every test exercises it.
- Terms: the **session factory** is the function handing out short-lived
  database connections; one per request or job, closed after.

### Stop 12: `docker-compose.yml` + `scripts/` — the machine it runs on

Four containers: **Caddy** (the reverse proxy — the public doorman that
holds the TLS certificate and forwards traffic to the app), the app,
Postgres (never exposed publicly), and **ofelia** (the cron sidecar — a tiny
scheduler container that runs purge/backup/digest inside the others on a
timer). `scripts/` holds the ops tools: backup, digest, pricing refresh,
self-audit.
- Serves: NFR-08/09 (backups, 30-min deploy). Read first: docker-compose.yml
  itself with `docs/06-OPS-RUNBOOK.md` §1 beside it.
- Proof: the D10 restore drill log (runbook §4) and `tests/test_ops_scripts.py`.

### Stop 13: `web/routes_api_read.py` + `sdk/` + `mcp/` — the platform API

A customer's audit data leaves the product through exactly one door: a
scoped, read-only REST API (`GET /api/v1/audits...`), fronted by three
client shapes so nobody hand-rolls HTTP. The JS/TS package (`sdk/js/`) and
the Python package (`src/tokenops_cost_auditor/sdk/`) both auto-instrument
OpenAI/Anthropic calls to SEND usage in (counts only, FR-22 by
construction — prompt/completion text is never read); the same Python
package's sibling, `web/routes_api_read.py`, is what customers READ back
from, authenticated by a personal `rt_`-prefixed token or an OAuth
app (`web/routes_oauth.py`, authorization-code + PKCE). `mcp/server.py`
wraps the same read endpoints as two MCP tools (`list_audits`,
`list_findings`) for AI coding assistants.
- Serves: R-SDK-PLATFORM (S-0/S-1/S-6), FR-22 (every payload is counts and
  dollars only — the schema has no text column to leak).
- Read first: `list_audits()` in `routes_api_read.py` (the workspace-scoped
  query every read endpoint repeats), then `install_openai()` in
  `sdk/instrument.py` (the SEND side) and `TOOLS` in `mcp/server.py` (the
  MCP wrapping).
- Proof: `tests/test_developer_platform.py` (tokens, OAuth, the read
  endpoints), `tests/test_mcp.py`, `tests/test_sdk.py`.
- Terms: an **ingest key** (`ik_`) is write-only — it can SEND usage but
  never read anything back. A **read token** (`rt_`) is the reverse. **PKCE**
  is the OAuth extension that lets a public client (no client secret) prove
  it, not an attacker, is redeeming its own auth code.

### Stop 14: `web/routes_members.py` + `web/authz.py` — orgs

A **workspace** is the tenancy boundary every resource (audits, sources,
tokens) hangs off; every user starts as the sole `owner` of a workspace of
one (single-tenant is the default — orgs are opt-in, R-ORG). Growing a
workspace means an owner or admin invites a teammate by email; the invite
code is a secret shown once and stored only as a keyed HMAC, single-use via
an atomic UPDATE-where-unconsumed. Four roles gate PRODUCT actions only —
`owner` > `admin` > `member` > `viewer` — never the customer's LLM traffic
(X-01/X-02 stand; the audit ENGINE in Stops 3-4 never learns what a
workspace is).
- Serves: R-ORG (the bounded X-03 relaxation — CLAUDE.md rule 1's
  amendment), FR-32-adjacent workspace scoping.
- Read first: `_MATRIX` in `authz.py` (the whole role→permission table is
  ~6 lines), then `invite_member()` in `routes_members.py`.
- Proof: `tests/test_workspace_members.py`, `tests/test_workspace_invites.py`,
  `tests/test_rbac_journey.py` (every role's rendered surface + fail-closed
  mutations).
- Terms: **fail-closed** means a role without a permission gets a 403/hidden
  control, never a silently-degraded page. **RBAC** = role-based access
  control — here, roles decide who may invite/revoke/see billing, never
  what an LLM call may do.

### Stop 15: `services/flywheel/` — the learning ladder's data spine

Three pieces feeding the L0-L4 learning ladder (docs/12-FLYWHEEL.md Stage
3) without ever handling prompt/completion text: `frame.py` extracts the
ONE training-frame shape every rung will consume (counts, enums, opaque
ids only — a free-text column literally cannot ship, `schema_violations()`
enforces it at test time); `cohort.py` answers "which rungs may exist yet"
by counting consenting accounts against each rung's threshold (L0 is
n=1, live today — see `FindingFeedback`, the Applied/Dismissed labels a
customer leaves on a finding); `export.py` (FR-35) builds the
`CohortExportEnvelope` — aggregate features only, under a workspace
pseudonym distinct from the frame's user pseudonym, gated on EXPLICIT
opt-in (`workspaces.cohort_opt_in`, default false) and a k-anonymity floor
below which the export honestly refuses rather than ships a thin file.
- Serves: docs/12-FLYWHEEL.md Stage 3 (L0-L4 ladder), FR-35 (cohort
  export), R-F1-SIGNOFF (benchmark_sharing exclusion), FR-22 throughout.
- Read first: `extract()` in `frame.py` (the frame contract), then
  `status()` in `cohort.py` (the rung math), then `build()` in `export.py`
  (FR-35's envelope).
- Proof: `tests/test_flywheel.py`, `tests/test_cohort_export.py`.
- Terms: the **L0-L4 ladder** is docs/12's five-rung plan for how
  deterministic detectors (Stop 4) get progressively calibrated by
  customer feedback — L0 (label capture) is the only rung live today; L1+
  are gated behind population thresholds, not built on a calendar.
  **k-anonymity floor** means an export exists only once enough distinct
  opted-in workspaces are in it that no single one can be singled out.

### Stop 16: `services/statements/build.py` — the Savings Statement

One artifact a month, written for whoever signs the bill and never logs in:
`build()` assembles it from `compute()` in `services/dashboard/savings.py`
— the ONE implementation of the savings formula (never duplicated here). It
inherits the same headline-honesty law as the report (Stop 6, R-Q9): the
headline names VERIFIED savings only (derived from priced findings, Stops
3-4), customer-reported figures (a `FindingFeedback.savings_realized_usd`)
sit in their own labelled section and never blend into the headline, and
every figure names the audit it came from.
- Serves: PLAN-V15 V-D6 (the Savings Statement), R-Q9 (verified vs.
  customer-reported separation), FR-30 (equiv-spend line when metered
  billing can't be assumed).
- Read first: `build()` in `statements/build.py`, then `compute()` in
  `services/dashboard/savings.py` for the underlying arithmetic.
- Proof: `tests/test_statements.py`.
- Terms: **verified savings** are dollars the engine itself computed from
  priced findings — the only figure allowed in a headline. A
  **customer-reported** figure is what a user typed after applying a fix;
  useful for label quality (Stop 15's L0), never for a headline number.

---

Done? The acceptance bar (PLAN §0.1 WP-COMPREHEND): trace any report finding
to its detector and test, and explain Stops 1-7 aloud, plainly, in under
five minutes.
