# Requirements Specification — TokenOps Cost Auditor v1.0

Convention: FR = functional, NFR = non-functional. Every ID appears in
04-TRACEABILITY.md mapped to design components, code modules, and tests.
Priority: M = must (v1 blocks ship), S = should (v1 if time), C = could
(Phase 2 candidate).

## A. Ingestion

FR-01 (M) Accept file upload of LLM API logs via authenticated web UI;
formats: OpenAI JSONL export, Anthropic JSONL export, documented generic
CSV. Max 200MB per upload; reject others with actionable error.
FR-02 (M) Normalize all inputs to internal CallRecord model:
{ts, provider, model, prompt_tokens, completion_tokens, cached_tokens,
latency_ms, endpoint, request_id, tags{}}. Unknown fields preserved in
raw_extra JSONB.
FR-03 (M) Schema validation with per-row error report; audit proceeds if
≥95% rows valid; else fail with downloadable row-error file.
FR-04 (S) CLI ingestion path (`tokenops-cost-auditor audit file.jsonl --out report.pdf`)
for manual/concierge delivery.
FR-24 (M) [amendment 2026-07-17, R-ICP] Documented log-exporter scripts as first-class
onboarding deliverables, starting with a Claude Code local-log exporter
(scripts/exporters/claude_code_export.py): converts Claude Code session logs on disk
to TokenOps JSONL consumable by FR-01/FR-02 ingestion; no prompt/completion text in
output (FR-22 applies); tested against a checked-in session fixture.

## B. Analysis engine (deterministic; NO LLM calls — NFR-01)

FR-05 (M) Versioned, data-driven pricing table (YAML): provider × model ×
{input, output, cached} rates with effective-date ranges; unit-tested.
FR-06 (M) Compute per-call and aggregate cost: by model, by day, by tag/
endpoint; totals reconcile to ±0.5% of sum of parts (NFR-07).
FR-07 (M) Detector D1 oversized-model-for-task: flags frontier-model calls
whose completion length/route profile fits a cheaper model; est. savings.
FR-08 (M) Detector D2 missing-prompt-caching: repeated prompt prefixes
≥1024 tokens without cached_tokens; savings = cacheable × rate delta.
FR-09 (M) Detector D3 prompt-bloat: system/prompt token p50/p90 per route;
flags routes > configurable threshold above corpus norm.
FR-10 (M) Detector D4 retry-storm/duplicates: near-identical requests
within time window; counts + wasted $.
FR-11 (M) Detector D5 unbounded-max_tokens: declared max vs actual
completion distribution (when max present in logs) or provider-default
waste heuristic; flags.
FR-12 (M) Detector D6 chatty-loop: bursts of many small sequential calls
from same tag/session that are batchable; agent-loop signature (same file/
context re-read pattern via repeated prefixes) highlighted.
FR-13 (M) Each Finding = {id, detector, severity, monthly_cost_impact_usd,
evidence_row_refs[≤20 samples], fix_recommendation, confidence}.
Conservative estimation rules documented in-code and in report appendix.

## C. Reporting

FR-14 (M) Report artifact: JSON (machine) + branded PDF (client-ready):
executive summary (current spend, optimized projection, savings %), spend
charts (by model, by day), savings waterfall, findings ranked by $ impact,
methodology appendix, data-handling statement.
FR-15 (M) Web report page (signed URL, expiring) mirroring the PDF.
FR-16 (S) Shareable redacted sample report for marketing (synthetic data).
FR-28 (M) [amendment 2026-07-17, R-PRICING-OPS] Every report (JSON + PDF
methodology) prints pricing table version/last_verified and the count+list
of unpriced models encountered.
FR-32 (M) [amendment 2026-07-23, R-EXPLORER; extended same day by
R-MULTI-SOURCE] Report explorer: logged-in customers compose filtered views
over their ENTIRE retained history — filters: date range, grouping
(day/month), source tier OR a specific connected account (per-account
attribution via audits.source_id; pre-attribution audits stated honestly),
model, finding type, severity, feedback status. SSR + htmx in the dashboard shell. Laws
attached: filtered totals reconcile ±0.5% (NFR-07); purged audits
participate as retained aggregates + metadata, labeled (FR-21/FR-31);
per-view tier coverage stated honestly; FR-30 line renders when any audit
in view carries equiv-spend; overlapping audit coverage counted once
(latest audit wins per day×model bucket, NOTES-sheet derivation); FR-22
counts-only throughout. Saved views + export are a later slice (held on
PLAN-FLYWHEEL §6 Q6).

## D. Accounts, payments, admin

FR-17 (M) Email magic-link auth (no passwords v1). Session cookie, secure.
FR-18 (M) Payment before upload unlock: Razorpay payment link (INR) and
Stripe payment link (USD), env-gated; manual fulfillment acceptable;
webhook OR admin-manual mark-paid both supported.
FR-19 (M) Admin panel (token-protected): list users/audits/status, re-run
audit, mark-paid, trigger purge, download report.
FR-20 (S) Transactional email: magic link, report-ready notification
(SMTP/provider-agnostic port).
FR-25 (M) [amendment 2026-07-17, R-API] All API routes live under /api/v1/
(web pages unaffected).
FR-26 (M) [amendment 2026-07-17, R-API] Upload accepts optional
Idempotency-Key header; duplicate key for the same user returns the original
audit (201 first time, 200 replays); keys retained 7 days alongside upload
lifecycle.
FR-27 (M) [amendment 2026-07-17, R-API] Payment webhooks enforce timestamp
tolerance (5 min) and processed-event-id dedup (append-only table) in
addition to signature verification.

## E. Data lifecycle & security

FR-21 (M) Raw uploads auto-purged 7 days after report generation (daily
cron); purge events written to append-only audit_log. Derived aggregates
(no prompt content) retained.
FR-22 (M) No prompt/completion TEXT is ever persisted beyond raw file
lifetime; CallRecord stores counts/metadata only. [Founder amendment
2026-07-20, GRAND ORDER v2: extends verbatim to connector-pulled and
streamed data — the counts-only law applies at every ingestion tier's
door, including the OTLP path where prompt-content attributes are dropped
at ingest.]
FR-23 (M) Landing page states data policy verbatim: "analyzed then
deleted; nothing retained beyond 7 days; never used for training."
NFR-01 (M) Analysis engine contains zero LLM/API inference calls.
NFR-02 (M) TLS everywhere (Caddy auto-TLS); secrets via env only.
NFR-03 (M) Rate limiting on upload + auth endpoints.

## F. Performance, reliability, observability, ops

NFR-04 (M) 1M-row JSONL processed <= 11 min (660 s) on the reference
  single 4-vCPU VPS class. [Founder amendment 2026-07-20, D13 deploy: the
  production box (Contabo 4 vCPU / 7.8 GiB) measured 624 s end-to-end via
  the live HTTPS path — 4% over the original 600 s bound. We publish the
  honest number and amend the spec, never the reverse. Workstation-class
  reference (94.3 s) unchanged in docs benchmarks.]
NFR-05 (M) Structured JSON logging w/ request IDs; /healthz endpoint.
NFR-06 (M) Error tracking hook (Sentry-compatible, env-gated).
NFR-07 (M) Cost math reconciliation property tests (±0.5%).
NFR-08 (M) Daily pg_dump backup script + documented restore drill.
NFR-09 (M) Single-box docker-compose deploy (app, postgres, caddy);
documented runbook; deploy < 30 min from clean VPS.
NFR-10 (S) Background processing via FastAPI BackgroundTasks; job status
polling endpoint; no external queue in v1.
NFR-11 (M) All timestamps UTC; currency USD internally, INR display via
fixed configurable rate for invoices.
NFR-12 (M) [amendment 2026-07-17, R-API] Rate limiting keyed per
authenticated user where a session exists, per-IP otherwise; 429 responses
include Retry-After.
NFR-13 (M) [amendment 2026-07-17, R-API] Processing concurrency cap (config
MAX_CONCURRENT_AUDITS, default 2); audits beyond cap hold in queued status;
status API reflects queue position.
NFR-14 (M) [amendment 2026-07-17, R-API] Single documented JSON error
envelope for all /api/v1 errors {error: {code, message, request_id}};
docs-site API reference renders it.
NFR-15 (M) [amendment 2026-07-17, R-PRICING-OPS] prices.yaml carries a
top-level last_verified date; CI emits a loud warning (not failure) when
it is >14 days old; daily digest includes pricing-table age.
FR-29 (M) [amendment 2026-07-17, R-PRICING-OPS] scripts/pricing_refresh.py
(ops tooling, NOT engine code; NFR-01 untouched): fetches documented
source_urls, extracts candidate rates, produces a human-readable DIFF vs
prices.yaml (new models, changed rates, unreachable pages). NEVER writes
prices.yaml. Weekly per runbook §8; failures surface in digest.

FR-30 (M) [amendment 2026-07-18, R-EQUIV-SPEND] Whenever metered-API
billing cannot be assumed for the audited traffic (e.g. Claude Code exports),
the report header and methodology carry verbatim: "Figures are API-equivalent
token value; actual billing depends on your plan."

FR-31 (M, v1.5) [founder amendment 2026-07-20, GRAND ORDER v2 / WP-2]
"My audits" history view for logged-in users, folded into the /dashboard.
Purged audits (FR-21) appear as metadata-only rows (counts, dates, status
— never content).

## G. Out of scope (recorded as requirements to NOT build)

X-01 Live proxy/gateway. X-02 Policy/budget enforcement. X-03 Multi-org
RBAC/SSO. X-04 LLM-generated narrative in reports. X-05 SPA frontend.
Violation of X-items in code review = reject PR.

[Founder amendment 2026-07-20, GRAND ORDER v2: for the v1.5 MONITOR build,
X-05 is relaxed ONLY to server-side rendering + htmx partials — no SPA
framework, no frontend build step. X-01/X-02 stand for the audit product
(alert-only budget observation in v1.5 is NOT enforcement; enforcement
remains forbidden). X-03/X-04 unchanged.]
