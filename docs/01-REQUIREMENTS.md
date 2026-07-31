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
FR-33 (M) [amendment 2026-07-25, R-DEPTH-ENGINE, founder "richer findings /
dynamic analysis"] Deterministic DEPTH detectors beyond the D1-D6 savings set,
all per-request-only (INACTIVE_ON_AGGREGATE) and INFORMATIONAL unless a
conservative net-loss is directly observed: D8 spend-concentration (the route
carrying the largest share of spend — where to optimise first; $0 claimed);
D9 ineffective-cache (cache written but rarely read = a conservative net cost
on OBSERVED billed tokens, disjoint from D2); D10 spend-anomaly (a day whose
spend is a robust temporal outlier — median+MAD, scale-free statistical +
materiality gates — vs the account's OWN daily baseline; catches unnamed cost
events the pattern detectors miss; $0 claimed). Same Finding schema (FR-13),
same privacy (FR-22), deterministic (X-04 — no LLM), engine-pure (T-NFR-01).
They POINT the customer at where to look; they never invent a saving number
for an unnamed cause.

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
deleted; nothing retained beyond 7 days; your logs and prompts are never used to train any model."
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

[Founder amendment 2026-07-23, R-ORG ("proceed with both"): X-03 is
RELAXED to permit enterprise org-management as PRODUCT GOVERNANCE only —
workspaces that own resources, members + invites, RBAC over who may
see/do things in the product, and SSO login (PLAN-ORG.md, slices
O-0..O-4). Hard boundary: roles never gate the customer's LLM traffic
(X-01/X-02 stand — no proxy, no enforcement); the audit engine stays
tenant-blind (tenancy at the web/persistence boundary, never inside
services/rules|pricing); single-tenant is the default, orgs opt-in.
X-04 unchanged.]

## H. Platform intelligence & enterprise scale [added 2026-07-28, R-MODEL-FACTORY + pillar-map consolidation]

All five requirements are advisory-layer only: X-01/X-02/X-04 unchanged; the
deterministic engine (NFR-01) and the no-text law (FR-22) are inherited, not
weakened. Tenancy stays at the web/persistence boundary (R-ORG). Each FR below
is sequenceable only via its QUEUE line (QUEUE law 5) and carries its
acceptance criteria inline (09-SDLC §2).

FR-34 (M) [R-MODEL-FACTORY] Model factory separation. All learned-model
  building, evaluation and improvement happens in a SEPARATE repository with
  its own eval-gated CI running on a daily schedule. The platform consumes
  versioned model artifacts through a loader behind a default-off flag; an
  artifact never ships unless it beats the deterministic baseline on the
  golden eval set, and it NEVER replaces deterministic money math (rule 4
  golden law intact). Until docs/12 §Stage-3 thresholds fire, the daily CI
  runs evals only — no training below threshold, ever ("no n=1 model").
  Accept: factory CI green daily; platform loader test proves flag-off = no
  behaviour change; eval report artifact per run.

FR-35 (M) [R-MODEL-FACTORY, R-ZTA] Cohort export with consent. Per-workspace
  explicit opt-in; export contains aggregate features ONLY (counts, ratios,
  percentiles — schema-versioned envelope), tenancy stripped at export time,
  k-anonymity floor n>=10 (the L1 threshold); this export is the ONLY data
  path into the factory. Accept: export golden fixture; consent-journey test;
  a below-floor cohort exports nothing and says why.

FR-36 (M) [R-MODEL-FACTORY, docs/12 INTENT+COPY LAW] Behaviour lens. Per-route
  workload-shape classification (agent-loop / retry-burst / context-growth /
  unclaimed-cache / steady) computed deterministically from counts, timing,
  model and cache fields only — never content. Surfaced on the breakdown page
  and the read API. Copy: dev depth is fix-first ("your pipeline, same output,
  lower bill"); owner depth stays money-verified. Accept: golden fixture per
  shape; ux gate passes both depths; engine purity test extends to the
  classifier.

FR-37 (M) [R-MODEL-FACTORY, R-Q9] Realized delta per finding. A finding
  labelled Applied (flywheel L0) receives its next-audit drift delta,
  attributed with provenance and rolled into the Savings Statement VERIFIED
  section. No measurable delta -> the finding stays "identified", never a
  fabricated figure. Accept: journey test upload->finding->apply->re-audit->
  statement shows the verified line with provenance.

FR-38 (S) [pillar-map 2026-07-28] Showback export. Finance-grade CSV of
  tag/route/model cost allocation including the pct_attributed coverage
  caveat, downloadable by billing-capable roles only (O-2 RBAC). Accept:
  export matches tokenomics goldens byte-for-byte; RBAC test; honest empty
  state when nothing is attributed.

## I. Enterprise deployment & zero-touch CI/CD [added 2026-07-28, R-ENT-DEPLOY — design home: docs/15]

All four are TRIGGER-GATED (docs/15 §8; triggers never dates). Zero-egress +
no-phone-home (R-DEPLOYMENT-CONTRACT 2–3) bind every customer-side clause.
Nothing below authorizes code before its trigger fires and the founder
sequences it.

FR-39 (S) [R-ENT-DEPLOY, R-MARKETPLACE a] Deployment modes. The product ships
  as ONE artifact behind five modes — in-perimeter CLI (shipped), hosted SaaS
  (shipped), VPC self-hosted compose (shipped)/Helm (gap), air-gap bundle
  (gap), marketplace IaC (gap) — config-only differences, BYO
  postgres/TLS/identity, engine bytes identical in every channel.
  Accept (per closing slice): install evidence named in docs/15 §4 ledger.

FR-40 (S) [R-ENT-DEPLOY, R-DEPLOY-AUTOMATION 2] Lane-A zero-touch release
  train: tag → signed image → gate-round → staging → smoke → promote →
  health-gated cutover with auto-rollback (docs/15 §7.5); backup-then-migrate
  order; additive-only migration law retained. Activation ONLY on the
  recorded trigger (>1 app from monorepo OR >1 deploy/week for a month);
  founder-gated promotion stands until then. Accept: drill tag reaches prod
  with zero human steps; induced health-fail rolls back automatically.

FR-41 (S) [R-ENT-DEPLOY] Lane-B customer zero-touch updates: pull-only signed
  semver channel, stable Helm values contract (docs/15 §7.2), pre-upgrade
  migration runner (§7.4), offline bundle path (§7.3), N-1
  upgrade/rollback-compatibility window. We never push, ping, or
  update-check. Accept: N-1→N→rollback cycle green against kind; offline
  install completes with zero network calls.

FR-42 (S) [R-ENT-DEPLOY, R-MARKETPLACE b] Scale claims discipline: public
  scale statements use MEASURED figures only (docs/15 §3 + its caveats);
  scaling dimensions are data volume + audit concurrency (+ Phase-2 policy
  throughput), never concurrent logins; rungs advance only on their named
  triggers. Accept: docs-site perf claims trace to a measured run; stale-era
  figures carry their caveat (six-detector detect timing flagged until
  re-measured).
