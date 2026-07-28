# Low-Level Design — TokenOps Cost Auditor v1.0

## 1. Package layout (src/tokenops_cost_auditor)

```
src/tokenops_cost_auditor/
  config.py            # pydantic-settings; all env vars documented
  main.py              # FastAPI app factory, middleware, routers
  web/                 # Jinja2 routes: landing, auth, upload, report, admin
    templates/         # base.html, landing, upload, report, admin, pdf/
  api/
    routes_upload.py   # POST /audits, GET /audits/{id}/status
    routes_webhooks.py # POST /webhooks/razorpay, /webhooks/stripe
  services/
    ingest/
      base.py          # LogParser protocol; detect_format()
      openai_jsonl.py  # FR-01/02
      anthropic_jsonl.py
      generic_csv.py
      normalizer.py    # -> CallRecordFrame (pyarrow/pandas)
      validator.py     # FR-03 row errors
    pricing/
      table.py         # PricingTable.load(yaml), rate(provider,model,date)
      data/prices.yaml # versioned rates, effective_from per entry
      coster.py        # add cost columns; reconcile check (NFR-07)
    rules/
      base.py          # Detector protocol: run(frame, ctx)->list[Finding]
      d1_oversized_model.py
      d2_missing_cache.py
      d3_prompt_bloat.py
      d4_retry_storm.py
      d5_unbounded_max_tokens.py
      d6_chatty_loop.py
      registry.py      # ordered registry; enable flags in config
      findings.py      # Finding dataclass (FR-13); estimator helpers
    report/
      model.py         # ReportModel assembly
      render_json.py
      render_pdf.py    # weasyprint on templates/pdf/report.html
      signer.py        # itsdangerous signed URLs (FR-15)
    lifecycle/
      purge.py         # purge_due_uploads(); called by cron entrypoint
      auditlog.py      # append-only writer
    payments/
      base.py          # PaymentPort
      razorpay_link.py
      stripe_link.py
    mail/
      base.py          # MailPort
      smtp.py
    runner.py          # AuditRunner: orchestrates 3.1 pipeline
  persistence/
    models.py          # SQLAlchemy: users, audits, findings,
                       # call_aggregates, audit_log, payments
    repo.py            # thin repositories
    migrations/        # alembic
  obs/
    logging.py         # structlog config, request-id middleware
    errors.py          # sentry hook (env-gated)
    ratelimit.py       # slowapi limiter
  cli.py               # `tokenops-cost-auditor audit file --out report.pdf` (FR-04)
```

## 2. Core types

CallRecordFrame: pandas DataFrame with columns
[ts:datetime64[UTC], provider:str, model:str, prompt_tokens:int,
completion_tokens:int, cached_tokens:int, latency_ms:float|NaN,
endpoint:str, request_id:str, tag:str, prefix_hash:str|None,
declared_max_tokens:int|NaN, cost_usd:float(added by coster)]

Finding(id, detector:str, severity:enum[low|med|high],
monthly_cost_impact_usd:float, confidence:enum[conservative|estimated],
evidence:list[EvidenceRef(≤20)], fix_text:str)
EvidenceRef = {row_idx, ts, model, tokens, note} — counts only, FR-22.

## 3. Detector algorithms (deterministic; thresholds in config)

D1 oversized-model: group by (tag,endpoint); for frontier models
(config list), compute completion p50; if p50 < SHORT_COMPLETION_T (default
150 tok) AND no cached reasoning marker → candidate; savings = calls ×
(rate_frontier − rate_suggested) applied to token means. Suggested model
mapping table in config (e.g. opus→sonnet, gpt-x→mini tier).
Confidence=estimated.

D2 missing-cache: requires prefix_hash (from text when present) else
prompt_tokens equality heuristic: bucket by (model, prompt_tokens) with
count ≥ CACHE_MIN_REPEATS (default 25) and prompt_tokens ≥ 1024 and
cached_tokens == 0 → cacheable share = (prompt_tokens − delta_est) ×
(input_rate − cached_rate). Confidence=conservative when hash-based.

D3 prompt-bloat: per (tag,endpoint): if p90 prompt_tokens > BLOAT_MULT
(default 2.0) × corpus median for similar completion sizes → flag; savings
= excess tokens × input_rate × 0.5 safety factor.

D4 retry-storm: sort by (tag, prefix_hash|prompt_tokens, model); windows of
WINDOW_S (default 120s) with ≥ DUP_MIN (default 3) near-identical calls;
wasted = (n−1) × mean cost. High severity if any window ≥10.

D5 unbounded-max: where declared_max_tokens present: flag routes with
declared_max ≥ 4× completion p95; waste is latency/risk note + $0 direct
(informational) unless provider bills reserved (config flag).

D6 chatty-loop: per tag/session (session = tag+15min gap split): runs of
≥ LOOP_MIN (default 8) calls each < 300 completion tokens within 10 min;
plus agent re-read signature: same prefix_hash ≥5 times in session.
Savings = batchable estimate (n_calls − ceil(n/BATCH_SZ)) × overhead
tokens × rate. Flags "agent loop suspected" when re-read signature fires.

## 4. AuditRunner sequence (runner.py)

```
run(audit_id):
  set status=processing; t0
  frame = ingest.load(path)                # raises IngestError -> failed
  vr = validator.validate(frame)           # FR-03; abort if <95% valid
  frame = coster.apply(pricing_table, frame)
  reconcile(frame)                          # NFR-07 assertion
  findings = registry.run_all(frame, ctx)
  aggregates = aggregate(frame)             # persist call_aggregates
  report = ReportModel.build(audit, frame, findings, aggregates)
  render_json(report); render_pdf(report)
  persist findings; status=done; report_ready_at=now
  mail.report_ready(user, signed_url)
  auditlog("audit.completed", ...)
```
Failure path: status=failed, error persisted, admin notified, user email
with support contact. Idempotent re-run from admin (FR-19).

## 5. API contract (v1)

POST /api/audits            multipart file; -> {audit_id} (auth, paid,
                            ratelimited, 200MB cap)
GET  /api/audits/{id}/status -> {status, valid_pct?, error?}
GET  /r/{signed}            web report (FR-15)
POST /webhooks/razorpay     signature-verified; mark payment
POST /webhooks/stripe       signature-verified; mark payment
GET  /healthz               {ok, db, disk_free}
Admin (X-Admin-Token): GET /admin, POST /admin/audits/{id}/rerun,
POST /admin/audits/{id}/purge, POST /admin/payments/mark-paid

## 6. DB schema notes

All tables UTC timestamps; audits.purged_at set by lifecycle; FK cascade
user→audits; findings.evidence_sample JSONB ≤ 20 items enforced at write;
audit_log has no UPDATE/DELETE grants (append-only by role).

## 7. Config (env) — exhaustive list in config.py

APP_ENV, SECRET_KEY, DATABASE_URL, UPLOAD_DIR, REPORT_DIR,
MAX_UPLOAD_MB=200, PURGE_AFTER_DAYS=7, ADMIN_TOKEN,
RAZORPAY_*(gated), STRIPE_*(gated), SMTP_*(gated), SENTRY_DSN(gated),
detector thresholds (D1..D6 as §3), INR_PER_USD_DISPLAY.

## 8. Error taxonomy

IngestError(format/row), PricingGapError(model missing → report lists
"unpriced models", audit continues, severity note), RenderError,
PaymentVerifyError. All mapped to user-safe messages; internals to logs.

## 9. Platform-intelligence contracts [2026-07-28, R-MODEL-FACTORY — Fable design pass; per-slice detail expands at each slice's design gate]

### 9.1 CohortExportEnvelope v1 (FR-35)
```
{ "schema_version": "1.0", "period": "YYYY-MM",
  "workspace_ref": "<opaque salted hash — never the id>",
  "k": <int, cohort size at export; envelope EXISTS only when k>=10>,
  "features": { "monthly_spend_usd": float, "tokens_in|out|cached": int,
    "cache_hit_rate": float, "out_in_ratio": float,
    "detector_fire_rates": {"d1".."d10": float},
    "shape_mix": {"agent_loop|retry_burst|context_growth|unclaimed_cache|steady": float} } }
```
No names, no routes, no tags, no text — ratios and counts only (R-ZTA).
Consent: `workspace.cohort_opt_in` (default false), checked at export time.

### 9.2 ModelArtifactPort (FR-34)
`load(name: str, version: str) -> ArtifactHandle` — verifies sha256 + semver
against a pinned manifest; raises on mismatch; returns None when
`model_artifacts_enabled` is false (callers must handle None = deterministic
path). Artifacts carry `eval_report.json` (baseline_delta must be > 0 to
promote — enforced factory-side AND re-checked at load).

### 9.3 ShapeClass (FR-36)
`Enum {AGENT_LOOP, RETRY_BURST, CONTEXT_GROWTH, UNCLAIMED_CACHE, STEADY}` ·
`classify(route_rows: pd.DataFrame) -> ShapeResult(cls, rationale: str)` —
thresholds in config (like detector thresholds §3), rationale is a fixed
template string naming the counts that fired it (no probabilities, no
inference). Ships beside tokenomics.py; import-guard covered.

### 9.4 RealizedDelta (FR-37)
Join key: (workspace_id, detector, route/model scope) — L0 verdict row ×
drift delta between the audit that raised the finding and the next completed
audit. Emitted as `VerifiedLine(amount_usd, finding_ref, from_audit, to_audit)`
consumed ONLY by statements/build.py (R-Q9: provenance = both audit ids).

### 9.5 Showback CSV (FR-38)
Columns: `dimension,name,calls,monthly_usd,share,pct_attributed_caveat` —
figures byte-identical to tokenomics goldens; route behind O-2
MANAGE_BILLING; empty allocation -> header row + honest comment line only.
