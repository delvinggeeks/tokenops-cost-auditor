# High-Level Design — TokenOps Cost Auditor v1.0

## 1. Architecture overview

Single-service modular monolith (FastAPI) + Postgres, deployed as
docker-compose on one VPS behind Caddy (auto-TLS). Deliberately boring:
no queue, no microservices, no SPA. Modularity preserved via strict
package boundaries so Phase 2 (gateway/policy engine) extends without
rewrite.

```
[Browser] --HTTPS--> [Caddy] --> [FastAPI app]
                                    |-- web (Jinja2 pages: landing, auth,
                                    |        upload, report, admin)
                                    |-- api (upload, job status, webhooks)
                                    |-- services
                                    |     |-- ingest  (parsers/normalizer)
                                    |     |-- pricing (versioned table)
                                    |     |-- rules   (D1..D6 detectors)
                                    |     |-- report  (JSON/PDF/web render)
                                    |     |-- lifecycle (purge cron)
                                    |     |-- payments (razorpay/stripe)
                                    |     |-- mail    (SMTP port)
                                    |-- persistence (SQLAlchemy models,
                                    |                Alembic migrations)
                                    |-- obs (logging, healthz, errors)
                              [Postgres 17]   [Local disk: uploads/, reports/]
```

## 2. Component responsibilities (maps to REQ groups)

C1 Web/UI (Jinja2, server-rendered): landing (FR-23), auth (FR-17),
upload flow (FR-01), report page (FR-15), admin (FR-19).
C2 Ingest service: format detection, parsers (openai_jsonl,
anthropic_jsonl, generic_csv), normalizer → CallRecord (FR-02), row
validation + error file (FR-03), CLI entry (FR-04).
C3 Pricing service: YAML-loaded PricingTable with effective dates (FR-05),
cost computation (FR-06, NFR-07).
C4 Rules engine: Detector protocol; registry of D1..D6 (FR-07..FR-12);
emits Finding objects (FR-13). Pure functions over CallRecord frames
(pandas/pyarrow), no I/O, no network (NFR-01).
C5 Report service: assembles ReportModel; renders JSON, weasyprint PDF,
web view; signed expiring URLs (FR-14, FR-15).
C6 Lifecycle service: purge cron (FR-21), audit_log writer (FR-21),
retention guarantees (FR-22).
C7 Payments: provider-agnostic PaymentPort; RazorpayLinkAdapter,
StripeLinkAdapter; webhook receiver + admin manual mark-paid (FR-18).
C8 Mail: MailPort + SMTP adapter (FR-20).
C9 Obs/Ops: structlog JSON logs, request-ID middleware, /healthz
(NFR-05), Sentry hook (NFR-06), rate limiting (NFR-03), backup script
(NFR-08).

## 3. Key data flow (audit happy path)

1 upload (auth'd, paid) → file saved to uploads/{audit_id} → Audit row
(status=queued) → 2 BackgroundTask: ingest → CallRecord frame →
3 pricing: cost columns → 4 rules: findings[] → 5 report: JSON + PDF to
reports/{audit_id} → Audit status=done → 6 mail: report-ready link →
7 day+7 cron: purge uploads/{audit_id}, log purge event.

## 4. Data model (persistence overview; detail in LLD)

users(id, email, created_at)
audits(id, user_id, status[queued|processing|done|failed], provider_mix,
  row_count, valid_pct, total_spend_usd, projected_spend_usd,
  savings_pct, paid_via, created_at, report_ready_at, purged_at)
findings(id, audit_id, detector, severity, monthly_impact_usd,
  confidence, fix_text, evidence_sample JSONB)
call_aggregates(audit_id, day, model, calls, prompt_tokens,
  completion_tokens, cached_tokens, cost_usd)   -- aggregates only, FR-22
audit_log(id, ts, actor, action, subject, detail JSONB)  -- append-only
payments(id, user_id, provider, ref, amount, currency, status, ts)
NOTE: raw CallRecords live only in-memory/parquet temp during processing;
never row-persisted (FR-22). Evidence samples store token COUNTS and
hashes of prefixes, not prompt text.

## 5. Technology decisions (ADR summary)

ADR-1 Monolith over services: solo founder, 14-day target, one box.
ADR-2 Server-rendered Jinja2 over SPA: speed, SEO for landing, X-05.
ADR-3 pandas/pyarrow in-memory analysis over DB-side SQL: 1M rows fits
RAM; simpler detector code; NFR-04 met.
ADR-4 weasyprint for PDF: HTML template reuse between web + PDF.
ADR-5 BackgroundTasks over Celery/queue: one worker adequate; upgrade
path = swap AuditRunner behind interface (Phase 2).
ADR-6 Payment links over full checkout integration: 14-day scope; webhook
+ manual mark-paid covers v1.
ADR-7 Prefix-hash technique for cache/duplicate detection: SHA-256 over
first N tokens' text when text present in logs, else token-count
heuristics; guarantees FR-22 (no prompt text persisted).

## 6. Security model

Auth: magic link (signed, 15-min expiry, single-use) → session cookie
(HttpOnly, Secure, SameSite=Lax). Admin: separate long random token via
env, IP-logged. Uploads: size cap, extension+content sniff, stored
outside web root. Reports: signed URL w/ expiry. Secrets: env only.
Postgres: local network only (compose network), no public port.

## 7. Scale & evolution path (Phase 2 hooks)

Interfaces already isolated: IngestPort (add proxy-stream source),
AuditRunner (swap to queue), PaymentPort (subscriptions), Detector
registry (add detectors without core change). Gateway/policy engine
becomes a sibling service consuming the same pricing + rules packages.
