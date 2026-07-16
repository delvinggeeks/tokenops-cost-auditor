# Test Plan — TokenOps Cost Auditor v1.0

Strategy: money math and detectors are the product — they get golden-file
and property tests. No LLM = no eval suite needed = fully deterministic CI.

## 1. Test levels

L1 Unit (pytest): parsers, pricing, each detector, estimators, signer.
L2 Integration: AuditRunner end-to-end on synthetic fixtures (upload →
JSON/PDF artifacts) against a real Postgres (docker service in CI).
L3 API: FastAPI TestClient — auth, upload, status, webhooks, admin.
L4 Performance: 1M-row generated fixture; assert wall-clock < 10 min on CI
runner class documented (NFR-04; threshold env-scaled).
L5 Manual ops drills (logged in RUNBOOK): TLS check, backup+restore,
clean-VPS deploy < 30 min.

## 2. Fixtures

F1 openai_small.jsonl (500 rows, clean) · F2 anthropic_small.jsonl ·
F3 mixed_dirty.jsonl (8% invalid rows → FR-03 path) · F4 generic.csv ·
F5 waste_pack.jsonl — synthetic traffic engineered so EACH detector fires
with KNOWN expected savings (golden numbers asserted exactly) ·
F6 clean_optimal.jsonl — zero findings expected (false-positive guard) ·
F7 perf_1m.jsonl.gz (generated in CI by script, seeded RNG).

## 3. Key test cases (IDs referenced by traceability matrix)

T-ING-01..04: format detection per fixture; oversize file rejected;
wrong extension rejected; empty file actionable error.
T-ING-05..07: normalization column mapping per provider; raw_extra
preserved; UTC coercion.
T-ING-08..09: dirty fixture → row-error file contents; <95% valid aborts.
T-PRC-01..03: rate lookup incl. effective-date boundaries; unknown model →
PricingGapError path lists model in report.
T-PRC-04: per-call cost golden values (hand-computed spreadsheet checked
into fixtures/pricing_golden.csv).
T-PRC-05 (property, hypothesis): sum(parts) reconciles to total ±0.5%
across random frames.
T-RUL-00: registry runs all detectors, ordering stable, disable flag works.
T-RUL-D1..D6: per detector: (a) fires on waste_pack with EXACT golden
savings, (b) silent on clean_optimal, (c) threshold boundary case.
T-RUL-EV-01: Finding evidence ≤20 items; contains NO prompt text (assert
absence of any text field) — enforces FR-22 at test level.
T-REP-01..04: ReportModel numbers == engine numbers (no re-computation in
render layer); PDF renders non-empty, contains exec-summary savings %;
JSON schema validated; methodology appendix present.
T-REP-05..06: signed URL valid/expired/tampered.
T-AUTH-01..04: magic link issue/consume/single-use/expiry; session cookie
flags (HttpOnly/Secure).
T-PAY-01..05: webhook signature valid/invalid; mark-paid unlocks upload;
unpaid upload blocked (402); admin manual mark-paid.
T-ADM-01..04: token required; rerun idempotent; purge action; list view.
T-LIF-01..03: purge selects only due audits; files removed; audit_log
entry written; purged_at set.
T-LIF-04: call_aggregates contain counts only.
T-NFR-01 (import guard): static test asserts no anthropic/openai/httpx
inference imports inside services/rules and services/pricing.
T-NFR-03: burst upload hits 429.
T-OBS-01..03: request-id present in log lines; /healthz degrades when DB
down; sentry hook called on unhandled error (mocked).
T-PERF-01: perf fixture wall-clock bound.
T-API-01..02: upload happy path; status polling transitions
queued→processing→done.
T-WEB-01: landing contains verbatim data-policy string (FR-23).
T-CLI-01: CLI produces PDF from F1.

## 4. CI pipeline (GitHub Actions)

jobs: lint(ruff) → type(mypy strict on services/*) → unit+integration
(postgres service) → coverage gate (85% services, 100% money-math files) →
perf (nightly only) → build image → (manual) deploy.
PR template includes: traceability row added? X-scope violated? evidence
of golden-number update reviewed (money-math changes require spreadsheet
diff attached).

## 5. UAT (days 10–12)

UAT-1: founder's own Claude Code logs — full audit, review every finding
manually for sanity (this is the dogfood gate; publishable as content).
UAT-2: one friendly external design partner log set (free audit) — verify
export instructions comprehensible without a call.
Exit criteria: zero false-positive findings judged embarrassing; report
readable by a non-founder CTO in <10 minutes.
