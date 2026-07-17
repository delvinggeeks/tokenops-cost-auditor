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

Looks up each call's model in a hand-verified price file (`data/prices.yaml`)
and computes its dollar cost from the four token counts. Models not in the
file are listed as "unpriced" and excluded — never guessed.
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

### Stop 4: `src/tokenops_cost_auditor/services/rules/` — the six detectors

Six independent modules (`d1_...` to `d6_...`) each scan the priced frame
for one waste pattern and emit "findings" with a conservative dollar
estimate. `registry.py` runs them in order; `findings.py` holds the shared
building blocks (severity thresholds, evidence sampling, the as-billed token
rate).
- Serves: FR-07..FR-12 (one per detector), FR-13 (ranked findings).
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

One payment = one audit credit, consumed atomically at upload (two
simultaneous uploads cannot spend one credit — the database update itself is
the lock). Webhooks from Razorpay/Stripe are verified with ~30 lines of
standard-library HMAC, time-boxed, and deduplicated in an append-only table.
- Serves: FR-18/27. Read first: `claim_credit()` in `payments/base.py`.
- Proof: `tests/test_payments.py`.
- Terms: a **webhook** is the payment provider calling OUR server to say
  "someone paid". **HMAC** is a keyed checksum proving the call really came
  from the provider.

### Stop 10: `src/tokenops_cost_auditor/web/routes_admin.py` — your panel

Token-gated (wrong token sees 404, not a login page): list audits, re-run,
purge, mark-paid, download PDF. Every action lands in the audit log with the
caller's IP.
- Serves: FR-19/20. Read first: `admin_actor()` (the gate). Proof:
  `tests/test_payments.py` (TestTADM classes).

### Stop 11: `src/tokenops_cost_auditor/persistence/` — the database layer

`models.py` defines the 8 tables; `repo.py` holds the small helpers routes
call instead of touching the database directly; `migrations/` holds the
numbered schema-change scripts (a **migration** = a versioned script that
alters tables; ours only ever ADD, never drop, so rollback is just running
older code).
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

---

Done? The acceptance bar (PLAN §0.1 WP-COMPREHEND): trace any report finding
to its detector and test, and explain Stops 1-7 aloud, plainly, in under
five minutes.
