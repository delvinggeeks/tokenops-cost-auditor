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
FR-04 (S) CLI ingestion path (`tokenops audit file.jsonl --out report.pdf`)
for manual/concierge delivery.

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

## D. Accounts, payments, admin

FR-17 (M) Email magic-link auth (no passwords v1). Session cookie, secure.
FR-18 (M) Payment before upload unlock: Razorpay payment link (INR) and
Stripe payment link (USD), env-gated; manual fulfillment acceptable;
webhook OR admin-manual mark-paid both supported.
FR-19 (M) Admin panel (token-protected): list users/audits/status, re-run
audit, mark-paid, trigger purge, download report.
FR-20 (S) Transactional email: magic link, report-ready notification
(SMTP/provider-agnostic port).

## E. Data lifecycle & security

FR-21 (M) Raw uploads auto-purged 7 days after report generation (daily
cron); purge events written to append-only audit_log. Derived aggregates
(no prompt content) retained.
FR-22 (M) No prompt/completion TEXT is ever persisted beyond raw file
lifetime; CallRecord stores counts/metadata only.
FR-23 (M) Landing page states data policy verbatim: "analyzed then
deleted; nothing retained beyond 7 days; never used for training."
NFR-01 (M) Analysis engine contains zero LLM/API inference calls.
NFR-02 (M) TLS everywhere (Caddy auto-TLS); secrets via env only.
NFR-03 (M) Rate limiting on upload + auth endpoints.

## F. Performance, reliability, observability, ops

NFR-04 (M) 1M-row JSONL processed < 10 min on single 4-vCPU VPS.
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

## G. Out of scope (recorded as requirements to NOT build)

X-01 Live proxy/gateway. X-02 Policy/budget enforcement. X-03 Multi-org
RBAC/SSO. X-04 LLM-generated narrative in reports. X-05 SPA frontend.
Violation of X-items in code review = reject PR.
