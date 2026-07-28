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
T-ADM-01..05: token required; rerun idempotent; purge action; list view; report download (PDF, audit-logged).
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
[amendment 2026-07-17, R-API:]
T-API-03: every API route mounted under /api/v1; legacy paths 404.
T-API-04..05: Idempotency-Key first submit 201, replay 200 with same
audit_id; different users may reuse a key; keys purge with uploads.
T-API-06: audits beyond MAX_CONCURRENT_AUDITS hold queued; status API
reports queue position; positions advance as slots free.
T-API-07: all /api/v1 error paths return {error:{code,message,request_id}}.
T-PAY-06..07: webhook with stale timestamp (>5 min) rejected; duplicate
event id acknowledged but not reprocessed (append-only dedup table).
T-NFR-12: authenticated burst limited per user (not per IP); anonymous
burst limited per IP; 429 carries Retry-After.
[amendment 2026-07-17, R-PRICING-OPS:]
T-REP-08: report JSON + PDF methodology carry pricing version/last_verified
and unpriced-model count+list.
T-NFR-15: pricing-age checker warns (never fails) when last_verified >14d.
T-OPS-04: pricing_refresh diff logic on fixture pages (offline); output
lists new/changed/unreachable; never writes prices.yaml.
T-WEB-01: landing contains verbatim data-policy string (FR-23).
T-CLI-01: CLI produces PDF from F1.
[amendment 2026-07-28, T-F5 (FR-38) — vv gate note G-T-F5 f.1; the wider
FR-3x-era refresh of this doc is a registered QUEUE candidate:]
T-SHOW-01..06 (tests/test_showback.py, serializer): pinned CSV-byte golden
incl. CRLF; empty allocation → header + one comment line; json round-trip
byte-verbatim property on every money/share field; fixed-template caveat on
every row; model-before-route artifact order; comma/quote name CSV-quoting.
T-SHOW-07..12 (route + surface): owner 200 text/csv with attachment
filename; body byte-identical to on-disk artifact; every non-billing role
403 (O-2); no-audit / coarse-source / purged-artifact 404; FR-22
marker-absence on the CSV body; affordance owner-only and absent without
an artifact.
T-SHOW-13 (journey): upload → audit done → button → download → figures
match the artifact byte-for-byte.

[amendment 2026-07-28, T-F2 (FR-35) — tests/test_cohort_export.py:]
T-COH-01..04 (builder golden): exact envelope shape/values incl.
detector_fire_rates + shape_mix arithmetic; workspace_ref opaque/keyed/never
the id; DISTINCT HKDF context proven non-colliding with frame.py's user
pseudonym on the same raw id; missing-artifact honest fallback (audited
total_spend_usd + zeros, never a crash).
T-COH-05..08 (below-floor honesty): 9 vs 10 exact boundary; opted-out
workspaces never count toward k; out-of-period audits excluded; the refusal
names n and the floor.
T-COH-09 (determinism): two builds of the same DB state are byte-identical.
T-COH-10..12 (schema self-audit): a real envelope has zero violations; a
tampered free-text feature is caught; FEATURE_KEYS pinned to the LLD §9.1
contract.
T-COH-13..15 (consent journey): default off → absent from the export,
opt-in → present, opt-out → absent again; every flip audit-logged;
non-owner roles see no Settings toggle AND a forged POST 403s (O-2).
T-COH-16..19 (admin surface): token gate 404 without X-Admin-Token; a live
export over the real route; the below-floor honest JSON (envelopes: [] +
reason); the download is audit-logged; the admin-home row renders both
states.
T-COH-20 (FR-22): no prompt/completion/content substrings in the export
response.
T-COH-21 (engine purity, T-NFR-01): services/rules + services/pricing source
never contains "cohort"/"flywheel"; services/flywheel/*.py still imports no
rules/pricing/connectors/network.

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
