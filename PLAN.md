# PLAN.md — TokenOps Cost Auditor build plan (D1–D7 detailed, D8–D14 outline)

Status: **APPROVED by founder 2026-07-17, with rulings recorded below.**
Governing docs: docs/00–07, 09, 10. Gate protocol per docs/10-AGENT-HARNESS.md §3–4.
Author: Lokesh Prasanna Kumar S. Date: 2026-07-17.

---

## 0. Decisions of record

### 0.1 Founder rulings on §4 questions (2026-07-17, binding)

**R-Q1/Q2 GATE CADENCE — CONFIRMED by founder at D1 stop.** Gates fire only at
milestone-group boundaries — grouped rows gate ONCE, at the end of the group
(G2=end D3, G3=end D5, G4=end D7, G5=end D9). ux-reviewer window = D7–D9 inclusive;
architect UML emission at D6-architecture content happens at the G4 sweep (end of D7)
and at D13 — no dedicated architect run at D6. If D7 report work materially changes
component boundaries vs D6, that must be noted in the UML file header. Schedule in §2.

**R-Q3 PRICING SEED.** prices.yaml seeded from official OpenAI/Anthropic pricing pages
as of seed date; every entry carries `effective_from` + `# source_url:` comment. Golden
spreadsheet rows are founder-verified BEFORE the D2-D3 group gate runs — main thread
flags the founder when fixtures/pricing_golden.csv is ready for verification.

**R-Q4 CACHE RATES & D2 FORMULA.** Pricing schema carries FOUR rates per model:
`input, output, cache_write, cache_read`. D2 missing-cache savings is provider-aware:
`savings = repeats × cacheable_tokens × (input_rate − cache_read_rate)
         − est_writes × cacheable_tokens × (cache_write_rate − input_rate)`
where `est_writes` = one write per TTL window per unique prefix, conservatively
estimated from timestamps; if windows cannot be estimated, apply a **0.7 haircut** to
the estimate. Confidence label stays `conservative`. Documented in methodology appendix.

**R-Q5 CACHEABLE TOKENS.** Per bucket: verified common-prefix length when prefix-hash
evidence exists; otherwise `0.8 × min(prompt_tokens in bucket)` (fixed 20% suffix
haircut). Haircut documented in methodology appendix.

**R-Q6..Q12 DEFAULTS ACCEPTED, two guardrails:** (a) any default touching money math is
recorded in the golden spreadsheet **notes sheet** (applies to Q7 monthly extrapolation,
Q5/Q4 haircuts, Q6 prefix-hash length, Q10 bloat binning); (b) any default that
interacts with X-01..X-05 scope or FR-22 is ESCALATED to the founder, never defaulted.

**R-DEPS (founder, D1 stop).** Approved beyond the kickoff list: `pyyaml` (runtime,
D3 — FR-05 YAML pricing table) and `python-multipart` (runtime, D6 — FastAPI multipart
upload). `httpx` confirmed dev-only (TestClient). NO other dependency additions
without asking the founder first.

**R-ICP (founder, D1 stop — strategic update from docs/09b finding #2).** Primary ICP
is agent-fleet engineering teams (Claude Code/Codex logs on disk); log-exporter
scripts are FIRST-CLASS onboarding deliverables. Build consequences: (a) D2 adds a
documented Claude Code local-log exporter under `scripts/exporters/` with its own
fixture + test — new requirement FR-24 added to docs/01 with a traceability row
(founder amendment, approved); (b) D8 landing copy leads with the agent-fleet story;
(c) marketing stats policy per docs/09b §2: only the attributed 79%/98% figures are
used until dogfood numbers exist (docs/09 §6 amended accordingly).

**R-GOLDEN-C1..C4 (founder, 2026-07-17, golden-CSV verification corrections).**
(C1) GPT-5.6 family cache_write = 1.25x input (sol 6.25/terra 3.125/luna 1.25),
30-minute minimum cache life; zero-write-premium default restricted to GPT-5.5/5.4/
5.3 families; golden row G13 exercises the terra premium. (C2) gpt-5.3-codex
re-verified against source_url — explicitly listed, primary-source confidence.
(C3) v1 does NOT model OpenAI long-context surcharge (>272K: 2x input/1.5x output)
or regional data-residency multipliers (OpenAI post-Mar-2026 +10%; Anthropic
US-only 1.1x); the D7 report methodology appendix MUST state that spend estimates
are conservative floors (added to WP-D7 deliverables). (C4) D2 est_writes TTL
windows are per provider-family (config D2_TTL_WINDOWS: anthropic 300s, gpt-5.6
1800s; fallback D2_TTL_WINDOW_S), never a single global window.

**R-D1-MAP (founder, 2026-07-17, D1-detector frontier list + downgrade map).**
Data-driven in config, founder-maintained, entries dated like prices.yaml. Seeds:
Anthropic (within provider only): fable-5->opus-4-8; opus-4-8/4-7/4-6->sonnet-5
(current effective rate: intro to Aug 31, standard from Sep 1); opus-4-1/opus-4->
opus-4-8 (legacy uplift); sonnet-5/sonnet-4-6->haiku-4-5. OpenAI: gpt-5.5-pro/
gpt-5.4-pro->gpt-5.5; gpt-5.6-sol/gpt-5.5->gpt-5.6-terra; gpt-5.6-terra/gpt-5.4->
gpt-5.6-luna; gpt-5.4-mini->gpt-5.4-nano. RULES: (a) exactly ONE tier down, never
chained; (b) never cross providers; (c) savings at the suggested model's four-rate
card, confidence=estimated; (d) short-completion threshold stays LLD default
(p50 < 150 tok, config knob); (e) every D1 finding carries the caveat "model
suitability requires your own quality evaluation"; (f) unknown/unmapped frontier
models produce an informational finding with no savings number.

**R-API (founder, 2026-07-17, API hardening — spec'd before D6 lands).**
FR-25 /api/v1 route versioning; FR-26 idempotent uploads (Idempotency-Key,
201-then-200 replays, 7-day key retention with upload lifecycle); FR-27 webhook
timestamp tolerance (5 min) + processed-event-id dedup (append-only) atop HMAC;
NFR-12 rate-limit keying user-else-IP with Retry-After on 429; NFR-13
MAX_CONCURRENT_AUDITS admission (default 2, queued status + queue position);
NFR-14 uniform /api/v1 error envelope {error:{code,message,request_id}} rendered
in the docs-site API reference. Tests T-API-03..07, T-PAY-06..07, T-NFR-12
(docs/05 amended). Lands: FR-25/26 + NFR-12/13/14 at D6; FR-27 at D9. Still OUT
with recorded triggers (BACKLOG.md): API keys (first request = buying signal,
notify founder), queue/workers (cap saturation), orgs/SSO (first team customer),
SOC2 (procurement blocker).

**R-PRICING-OPS (founder, 2026-07-17, pricing-table operations, v1 scope).**
NFR-15 last_verified in prices.yaml + CI loud warning (never failure) at >14 days
+ digest age line (D10). FR-28 every report prints pricing version/last_verified +
unpriced-model count/list (D6 JSON, D7 PDF methodology). FR-29
scripts/pricing_refresh.py read-only diff tool (fetch source_urls -> candidate
rates -> human-readable diff; NEVER writes prices.yaml; weekly per runbook §8;
failures in digest; lands D10). Docs-site pricing page presents human-verified
versioned pricing as a TRUST FEATURE: live/scraped pricing refused for money math
by design.

**R-PRICING-AGENT (founder, 2026-07-17) — WP-P1.5, FIRST post-launch package
(week 3-4), NOT in D1-D14.** FR-29b pricing-watch pipeline (ops-side only):
ofelia crawl 2x/week of source_urls + LiteLLM model-prices JSON cross-check
tripwire; snapshots archived with hashes; candidates -> pricing_candidates table
(pending_review); admin side-by-side diff, one-click approve; approval writes
prices.yaml entry (effective_from + source), auto-drafts golden-row suggestion,
bumps last_verified. HARD RULES: no auto-approval path exists in code; crawler
has zero write access to prices.yaml; LLM-assisted extraction only into the
candidate queue; cross-check disagreements flagged, never auto-resolved; every
approval audit-logged with founder as actor.

**R-SEQ-D6D7 (founder, 2026-07-17).** Proceed with D6-D7 group now, incorporating
R-API D6 items and FR-28 into D7 report deliverables; python-multipart lands at
D6 (approved). D-DOCS starts after G4 passes. G4 = architect (+UML emission),
vv-engineer, ux-reviewer at end of D7; report verdicts WITH a dogfood-readiness
assessment for UAT-1.

**R-SEQ-UAT1 (founder, 2026-07-17).** UAT-1 is founder-executed NOW, in parallel
with the build (CLI path on real Claude Code logs). Founder feedback = a
mini-milestone with its own fixes before D11-D12 formal UAT; expected follow-ups:
verified pricing rows for older model generations, D4/D6 threshold calibration.
D8-D9 build proceeds immediately (incorporating the architect's repo-pattern
note); G5 at end of D9 as scheduled. D-DOCS starts AFTER G5 (so it can include
founder-approved dogfood numbers and single-source the D8 legal pages).
STANDING REMINDER: T-PERF-01 is nightly-only; at least one successful nightly
perf run must exist before D-DOCS fills the benchmarks page (MP-6 precondition).

**R-PAY HMAC FIXTURES.** T-PAY signature tests must use known-good HMAC fixtures
computed independently of the implementation under test (fixtures generated by a
standalone script/reference values, never by calling the code being tested).

**R-MP9 (founder, 2026-07-17).** Legal single-sourcing CONFIRMED as built: web
templates (templates/legal/*.html) are the authoritative masters; docs-site
mirrors with drift-failing sync tests (tests/test_docs_site.py). No rendering-
pipeline dependency. Do not flip.

**R-PERF-MANUAL (founder, 2026-07-17).** T-PERF-01 triggered manually now
rather than waiting for the nightly schedule (amends the R-SEQ-UAT1 nightly
precondition). On pass: fill MP-6 with measured numbers, machine spec stated,
and clear that MEASUREMENT-PENDING item.

**R-D11-12-PARTIAL (founder, 2026-07-17).** D11-D12 authorization is PARTIAL:
after the perf run, proceed with everything not requiring founder input — UAT
harness prep, export-instruction hardening, threshold-knob documentation, F7
perf fixture validation. UAT-1 itself is founder-executed by definition
(docs/05 §5); its exit criteria (zero embarrassing false positives; report
readable by a non-founder CTO in <10 minutes) CANNOT be self-certified. The
UAT-1/UAT-2 sign-off gate stays OPEN until the founder's dogfood report lands.

**R-UAT1-FIXES-ACCEPTED (founder, 2026-07-18).** All four UAT-1 dogfood defect
fixes accepted: D4 cache-active exclusion + completion-token fingerprint;
top-50 bounded rendering with explicit note (JSON complete);
effective_prompt_rate() tokens-priced-as-billed (golden blend recorded);
headline savings capped at monthly spend with verbatim METHODOLOGY disclosure.

**R-D6-AGG (founder, 2026-07-18).** D6 chatty-loop findings aggregate per
session/tag: ONE finding per session, monthly impact summed over its runs,
evidence sampled across constituent runs (≤20, counts only), run count stated
in the finding text; report.json retains per-run detail under the aggregated
finding. IDENTICAL per-session aggregation applies to D4. Golden updates
follow money-math discipline (expected counts/impacts + spreadsheet
derivations in the NOTES sheet).

**R-EQUIV-SPEND (founder, 2026-07-18 → docs/01 FR-30).** Whenever metered-API
billing cannot be assumed (e.g. Claude Code exports), the report header and
methodology carry verbatim: "Figures are API-equivalent token value; actual
billing depends on your plan." Also on the docs-site quickstart Claude Code
exporter path.

**R-SELF-AUDIT (founder, 2026-07-18) — WP-SELF, scheduled immediately after
D13 deploy (before/alongside D14).** Ops-side only; engine and X-01..X-05
untouched. (a) scripts/self_audit.py: exporter on THIS project's sessions →
CLI audit → append one row per run to self_audit/ledger.csv (date, sessions,
calls, observed API-equiv spend, findings by detector, est. monthly waste,
waste %) + archive report.json; manual/local-scheduler only, NOT part of the
product deployment. (b) docs-site "We audit ourselves" page (Engineering):
cumulative audited build cost, per-milestone waste trendline (chart from the
ledger at docs build; MEASUREMENT-PENDING until ≥3 ledger rows), the UAT-1
story incl. the 228% defect caught pre-launch, and the intervention
experiment (2-3 named UAT-1 recommendations applied to our own workflow,
before/after deltas once ≥2 post-intervention milestones exist). Mandatory
verbatim rails: the R-EQUIV-SPEND line; "n=1, uncontrolled — your logs are
the real test"; link to run the same audit. (c) Ledger rows are
money-adjacent: each published row requires a founder-verification tick,
logged like golden files. (d) D14 launch assets cite ONLY ledger-verified
numbers; the UAT-1 figures (26.2% waste, 13s on 158k calls, $5,289/mo est. on
$20.2k/mo API-equivalent) usable WITH the equiv-spend framing.

**R-SEQ-POST-SIGNOFF (founder, 2026-07-18).** UAT-1 sign-off OPEN (awaits the
founder's completed review sheet + both docs/05 §5 exit-criteria checkboxes);
D13 blocked until it lands. After the D6/D4 aggregation merges, uat1 review
artifacts are REGENERATED so the founder's pass reviews shipping behavior.
Post-sign-off sequence: D13 deploy per runbook §2 (incl. VPS-hardware perf
validation + concurrency memory check: 2x max-size audits vs 8GB) →
ops-engineer D13 gate → WP-SELF → D14 launch.

**R-TOOLCHAIN (founder, 2026-07-17, harness amendment → docs/10 §2 TE-11 +
all six agent charters).** Any gate check that executes, compiles, lints, or
type-checks code MUST run through the project toolchain (`uv run ...` against
the pinned interpreter), never the sandbox/system python. A finding produced by
any other interpreter is invalid by definition. When a reviewer and the main
thread disagree on a toolchain-dependent fact, the pinned-toolchain reproduction
is authoritative; the resolution is recorded in STATUS.md. (Origin: G5
cold-reviewer false-positive — PEP 758 syntax judged under sandbox Python 3.13
while the project pins 3.14.)

**R-NAMING (founder, 2026-07-17, strengthened same day).** The full name is used
EVERYWHERE — dirs, files, code, not just display strings: Python package
`src/tokenops_cost_auditor/`, distribution `tokenops-cost-auditor`, compose project
name, DB name/user, container user, image tags, logger names, CLI command
`tokenops-cost-auditor`. Because docs/03-LLD.md §1 and FR-04 previously spelled the
short forms, their path/command strings were updated to match this ruling (docs/01
FR-04, docs/03 §1 tree, docs/04 coverage rule, ux-reviewer charter path) — flagged for
founder review at the D1 stop. Git authorship: Lokesh Prasanna Kumar S only; no
co-author trailers; no AI references in commit metadata.

**MARKET REFRESH (founder-requested 2026-07-17).** Deep multi-source market research
re-run before build start; report lands in docs/09b-MARKET-RESEARCH-REFRESH.md with a
marked recommendations section; PRD amendments remain founder-written (change control).

### 0.2 Standing decisions

**PY-VERSION: Python 3.14** (kickoff permits 3.14 if pandas/pyarrow/weasyprint/psycopg
install cleanly). Verified 2026-07-17 on linux x86_64 with uv 0.11.18:

- `uv pip compile --python-version 3.14 --only-binary :all:` over the full kickoff
  dependency list resolves with wheels only (exit 0). 3.13 also resolves (fallback).
- Real install + import test on CPython 3.14.5: pandas **3.0.3**, pyarrow **25.0.0**,
  psycopg **3.3.4** (binary), weasyprint **69.0** — all OK.
- Docker base: `python:3.14-slim` + weasyprint system libs (pango/harfbuzz/gdk-pixbuf).
- Note: pandas 3.0 is a major version (copy-on-write default, string dtype). Greenfield
  code, so no migration burden; detectors written against 3.0 semantics from day one.

**GIT-FLOW** (updated for R-Q1): repo is not yet a git repo → `git init` is the first
D1 action. One branch per **gate group** (`d1-scaffold`, `d2-d3-ingest-pricing`,
`d4-d5-detectors`, `d6-d7-runner-report`, `d8-d9-auth-payments`, `d10-lifecycle`,
`d11-d12-uat`, `d13-deploy`, `d14-launch`). Gate agents receive `git diff main...HEAD`
(the group diff, written to a file), STATUS.md, and only their charter-named docs.
Merge to main after all scheduled gates PASS; tag `dN` at each milestone completion.
Each Dn still ends all-green (tests) before Dn+1 starts, per CLAUDE.md rule 6.
Conventional commits throughout.

**PAYMENT-SDKS: none.** Razorpay/Stripe webhook signatures are HMAC-SHA256 — verified
with stdlib `hmac`/`hashlib`. Payment links are static env-configured URLs. Keeps
dependency list exactly as the kickoff specifies; no third-party payment SDKs.

**CRON: ofelia sidecar** in docker-compose (runbook §1 allows "ofelia or host crontab").
Keeps deploy a single `docker compose up -d`, staging identical to prod. Jobs: purge
02:00 UTC, backup 02:30 UTC, daily digest (wired at D10).

**MAIL: port + log adapter default.** `MailPort` with a structured-log adapter when
SMTP_* unset (dev prints magic link / report link to logs); SMTP adapter env-gated
(FR-20). Runner (D6) depends only on the port, so mail order-of-build is not blocking.

**COVERAGE GATE mechanics**: pytest-cov can't express "85% on services/*, 100% on
coster.py + findings.py" in one flag → small `scripts/coverage_gate.py` parses
`coverage json` and enforces both thresholds (paths that don't exist yet are skipped,
so the gate is green at D1 and tightens automatically as packages appear).

**MYPY scope**: strict on `src/tokenops_cost_auditor/services/*` per docs/05 §4; standard elsewhere.

---

## 1. Work packages

Each WP lists: files to create, tests (IDs from docs/05-TEST-PLAN.md §3), and the gate
sweep that covers it (§2, per ruling R-Q1). Universal exit criteria for every Dn: suite
green locally + CI, docs/04-TRACEABILITY.md updated in the same commit as each
implemented requirement, STATUS.md paragraph written, context cleared per TE-9 before
Dn+1; the group's gate sweep must PASS before the group branch merges to main.

### WP-D1 — Scaffold from scratch

Goal: uv project, src layout per docs/03-LLD.md §1, compose stack, CI green, rules files.

Files:
- `pyproject.toml` (deps exactly per kickoff; ruff + mypy config; requires-python ">=3.14"),
  `uv.lock`, `.python-version`, `.gitignore`
- `CLAUDE.md` — ONLY the 7 kickoff items; TE-1..TE-10 + K-1..K-4 copied verbatim from
  docs/10 §2 and §5
- `STATUS.md` (TE-4 shared memory, one paragraph per milestone), `BACKLOG.md` (empty —
  scope-freeze parking lot)
- `src/tokenops_cost_auditor/__init__.py`, `config.py` (pydantic-settings; every var in docs/03 §7),
  `main.py` (app factory, request-id middleware, `/healthz` with db + disk_free checks)
- `src/tokenops_cost_auditor/obs/{logging.py,errors.py,ratelimit.py}` (structlog JSON, env-gated
  Sentry hook, slowapi limiter instance)
- Package skeleton (`__init__.py` only, no stub logic): `web/`, `api/`, `services/`
  (+ `ingest/ pricing/ rules/ report/ lifecycle/ payments/ mail/`), `persistence/`
- `src/tokenops_cost_auditor/persistence/models.py` (DeclarativeBase only), alembic init
  (`alembic.ini`, `persistence/migrations/`) — no tables yet, additive-only policy noted
- `Dockerfile` (multi-stage uv build on python:3.14-slim + weasyprint system libs),
  `docker-compose.yml` (caddy→app→postgres:17 + ofelia; postgres compose-internal only;
  volumes pgdata/uploads/reports/backups; json-file logging max-size 50m, max-file 5),
  `Caddyfile`, `.env.example` (every config.py var, secrets blank)
- `.github/workflows/ci.yml`: lint(ruff) → type(mypy) → tests(postgres:17 service) →
  coverage gate → build image; perf job schedule-gated (nightly only); manual deploy stub
- `scripts/coverage_gate.py`
- `tests/conftest.py`, `tests/test_smoke.py`

Tests: T-OBS-01..03 (request-id in log lines; /healthz degrades when DB down; Sentry hook
called on unhandled error, mocked). These are the "empty suite" that makes CI green.
Gates: **ops-engineer, spec-guard**.
Extra exit criteria: `docker compose config` valid; image builds in CI; no secrets in repo.

### WP-D2 — Ingest

Files:
- `services/ingest/{base.py,openai_jsonl.py,anthropic_jsonl.py,generic_csv.py,
  normalizer.py,validator.py}` — LogParser protocol + `detect_format()`; normalize to
  CallRecordFrame per docs/03 §2 (UTC coercion, raw_extra preserved, prefix_hash per
  ADR-7 when text present — hash computed in-memory, text never retained);
  validator emits per-row error file, aborts <95% valid (FR-03)
- Fixtures: `tests/fixtures/{openai_small.jsonl,anthropic_small.jsonl,mixed_dirty.jsonl,
  generic.csv}` (F1–F4) + generator script `tests/fixtures/gen_fixtures.py` (seeded RNG)
- Generic-CSV column contract documented in `generic_csv.py` module docstring (surfaced
  to customers via export docs at D12)
- R-ICP addition: `scripts/exporters/claude_code_export.py` (documented Claude Code
  local-log → TokenOps JSONL exporter, FR-24) + session-log fixture + tests T-EXP-01..02;
  traceability row added in the same commit

Tests: T-ING-01..04 (format detection, oversize reject, wrong extension, empty file),
T-ING-05..07 (column mapping per provider, raw_extra, UTC), T-ING-08..09 (dirty fixture
row-error file; <95% aborts).
Gates: none at D2 — covered by sweep **G2** at end of D3.

### WP-D3 — Pricing

Files:
- `services/pricing/{table.py,coster.py}`, `services/pricing/data/prices.yaml`
  (versioned; provider × model × {input, output, cached} with effective_from ranges)
- `tests/fixtures/pricing_golden.csv` — hand-computed spreadsheet (founder-verifiable;
  money-math commit discipline starts here: golden update + spreadsheet diff in commit msg)
- PricingGapError path: unknown model → audit continues, "unpriced models" listed (docs/03 §8)

Tests: T-PRC-01..03 (rate lookup, effective-date boundaries, unknown-model path),
T-PRC-04 (per-call golden values), T-PRC-05 (hypothesis property: sum of parts
reconciles ±0.5%, NFR-07).
Gates: sweep **G2** (vv-engineer, cold-reviewer) covering D2-D3 — golden spreadsheet
founder-verified BEFORE the sweep runs (R-Q3). Pricing schema: four rates per R-Q4.

### WP-D4 — Rules engine part 1 (highest-signal detectors)

Files:
- `services/rules/{base.py,findings.py,registry.py}` — Detector protocol, Finding
  dataclass + estimator helpers (FR-13; EvidenceRef ≤20, counts/hashes only — FR-22),
  ordered registry with enable flags
- `services/rules/d2_missing_cache.py`, `services/rules/d4_retry_storm.py` (docs/03 §3)
- Fixtures: `waste_pack.jsonl` v1 (D2+D4 traffic with KNOWN golden savings),
  `clean_optimal.jsonl` (F6, zero-findings guard) + generator additions

Tests: T-RUL-00 (registry order stable, disable flag), T-RUL-EV-01 (evidence ≤20, no
text fields — FR-22 at test level), T-RUL-D2-01..03, T-RUL-D4-01..02 (each: exact golden
on waste_pack / silent on clean_optimal / threshold boundary). D2 savings formula and
cacheable_tokens per R-Q4/R-Q5.
Gates: none at D4 — covered by sweep **G3** at end of D5.

### WP-D5 — Rules engine part 2 (complete detector set)

Files:
- `services/rules/{d1_oversized_model.py,d3_prompt_bloat.py,d5_unbounded_max_tokens.py,
  d6_chatty_loop.py}`; frontier-model list + suggested-model mapping in config
- `waste_pack.jsonl` v2 — all six detectors fire with golden numbers complete
- `tests/test_import_guard.py` — T-NFR-01: no anthropic/openai/httpx/requests inside
  services/rules and services/pricing (static AST/grep check)

Tests: T-RUL-D1-01..03, T-RUL-D3-01..02, T-RUL-D5-01..02, T-RUL-D6-01..03, T-NFR-01.
Gates: sweep **G3** (vv-engineer, spec-guard, cold-reviewer) covering D4-D5.

### WP-D6 — Runner end-to-end, aggregates, report JSON, status API

Files:
- `services/runner.py` — AuditRunner per docs/03 §4 (status transitions, failure path,
  idempotent re-run); wired via FastAPI BackgroundTasks (NFR-10, ADR-5)
- `services/report/{model.py,render_json.py}` — ReportModel assembled from engine
  outputs, render layer does NOT recompute money math
- `services/lifecycle/auditlog.py` (append-only writer; runner logs audit.completed)
- `services/mail/base.py` + log adapter (port only; SMTP at D8)
- `persistence/models.py` (users, audits, findings, call_aggregates, audit_log),
  `persistence/repo.py`, migration `001_initial`
- `api/routes_upload.py` — POST /api/v1/audits (FR-25 prefix; auth+paid enforcement
  stubs behind interfaces until D8/D9; 200MB cap, content sniff, rate-limited with
  NFR-12 user-else-IP keying + Retry-After), GET /api/v1/audits/{id}/status with
  queue position (NFR-13 MAX_CONCURRENT_AUDITS admission); FR-26 Idempotency-Key
  handling (persisted keys, 201/200 replay semantics); NFR-14 error envelope on
  every /api/v1 handler

Tests: T-API-01..02 (upload happy path; queued→processing→done), T-API-03 (/api/v1
mounting), T-API-04..05 (idempotency 201/200 replay), T-API-06 (concurrency cap +
queue position), T-API-07 (error envelope), T-NFR-12 (user-else-IP + Retry-After),
T-REP-01 (ReportModel numbers == engine numbers), T-REP-03 (JSON schema validated),
T-LIF-04 (aggregates counts only), T-NFR-03 (burst upload → 429), T-NFR-11 (UTC
everywhere, USD internal).
L2 integration: AuditRunner on F1/F5 against real Postgres (CI service).
Gates: none at D6 — covered by sweep **G4** at end of D7 (R-Q1 nuance: UML emitted there).

### WP-D7 — PDF + web report + signer + CLI

Files:
- `services/report/{render_pdf.py,signer.py}` (weasyprint on templates/pdf/report.html;
  itsdangerous signed expiring URLs)
- `web/templates/{base.html,report.html,pdf/report.html}` + print CSS — exec summary
  (spend, optimized projection, savings %), charts (by model, by day), savings waterfall,
  findings ranked by monthly $ impact, methodology appendix, data-handling statement.
  Methodology appendix MUST include the R-GOLDEN-C3 floors note: v1 excludes OpenAI
  long-context surcharge and regional data-residency multipliers → spend estimates
  are conservative floors
- `web/` report route GET /r/{signed} (FR-15)
- `cli.py` — `tokenops-cost-auditor audit file.jsonl --out report.pdf` (FR-04)
- Stretch (S): synthetic redacted sample report fixture (FR-16, T-REP-07)

Tests: T-REP-02 (PDF non-empty, savings % present), T-REP-04 (methodology appendix
incl. R-GOLDEN-C3 floors + haircut disclosures), T-REP-08 (FR-28 pricing version +
unpriced models in JSON + PDF),
T-REP-05..06 (signed URL valid/expired/tampered), T-CLI-01, T-REP-07 (S, stretch).
Gates: sweep **G4** (architect — emits docs/uml/*.mmd, vv-engineer, ux-reviewer)
covering D6-D7.

---

## 2. Gate schedule per gate group (resolved per founder ruling R-Q1/Q2)

Grouped rows gate ONCE, at the end of the group. Order within a sweep as listed. Every
gate receives: the group diff (`git diff main...HEAD` written to a file), STATUS.md, its
charter-named docs only. FAIL → fix in main thread → re-run that gate on the new diff
only (TE-10). Never per-prompt, never per-file. No gate spawns another agent (K-4).

| Gate sweep | Fires at end of | Gates (in order) | Notes |
|------------|-----------------|------------------|-------|
| G1 | D1  | ops-engineer, spec-guard | scaffold conformance |
| G2 | D3 (covers D2-D3) | vv-engineer, cold-reviewer | golden spreadsheet founder-verified first (R-Q3) |
| G3 | D5 (covers D4-D5) | vv-engineer, spec-guard, cold-reviewer | T-NFR-01 in force |
| G4 | D7 (covers D6-D7) | architect, vv-engineer, ux-reviewer | architect emits docs/uml/*.mmd here (D6 content — see R-Q1 nuance) |
| G5 | D9 (covers D8-D9) | ux-reviewer, cold-reviewer, spec-guard | ux window D7–D9 |
| G6 | D10 | ops-engineer, vv-engineer | outline |
| G7 | D12 (covers D11-D12) | vv-engineer (UAT evidence + perf) | outline |
| G8 | D13 | ops-engineer + architect (D13 UML refresh only) | outline |
| G9 | D14 | spec-guard (final traceability sweep) | outline |

---

## 3. D8–D14 outline (coarse; detailed packaging appended to PLAN.md at end of D7)

- **D8** Auth + landing: `web/` auth routes (magic link signed 15-min single-use,
  session cookie HttpOnly/Secure/Lax), `mail/smtp.py`, templates landing (PRD §4 copy,
  FR-23 verbatim policy string) + ToS/Privacy/DPA-lite. Tests T-AUTH-01..04, T-WEB-01,
  T-MAIL-01(S). Copy angles (founder-approved 2026-07-17): lead with the agent-fleet
  story (R-ICP); differentiation line vs auto-routers (Copilot Auto etc.): "routers
  pick a model; we find the other five kinds of waste — and prove it in dollars"
  (routing addresses only D1; D2-D6 waste classes are untouched by routers).
- **D9** Payments + admin: `payments/{base,razorpay_link,stripe_link}.py`,
  `api/routes_webhooks.py` (HMAC verify + FR-27 timestamp tolerance 5 min +
  processed-event-id dedup, append-only table), `web/` admin (X-Admin-Token),
  migration 002 (payments + webhook_events). Tests T-PAY-01..07, T-ADM-01..04.
- **D10** Lifecycle + ops: `lifecycle/purge.py`, ofelia job wiring, `scripts/backup.sh`,
  `scripts/daily_digest.py` (incl. NFR-15 pricing-age + FR-29 failure surfacing),
  `scripts/pricing_refresh.py` (FR-29, read-only diff; T-OPS-04). Tests T-LIF-01..03;
  manual drills T-OPS-01..02 logged.
- **D11** UAT-1 dogfood (founder's Claude Code logs); findings-quality fixes.
- **D12** UAT-2 external audit; export docs hardened; T-PERF-01 (1M fixture, NFR-04).
- **D13** Production deploy per runbook §2; smoke; UptimeRobot; T-OPS-03.
- **D14** Launch; spec-guard final sweep.

Test-ID completeness: every M-priority ID in docs/05 §3 is owned above —
D1: T-OBS-01..03 · D2: T-ING-01..09 · D3: T-PRC-01..05 · D4: T-RUL-00/EV-01/D2/D4 ·
D5: T-RUL-D1/D3/D5/D6, T-NFR-01 · D6: T-API-01..02, T-REP-01/03, T-LIF-04, T-NFR-03,
T-NFR-11 · D7: T-REP-02/04/05/06, T-CLI-01 · D8: T-AUTH-01..04, T-WEB-01 ·
D9: T-PAY-01..05, T-ADM-01..04 · D10: T-LIF-01..03 · D12: T-PERF-01 ·
manual: T-OPS-01..03. S-priority: T-REP-07 (D7 stretch), T-MAIL-01 (D8).

---

## 4. Spec ambiguities — numbered questions (RESOLVED)

All twelve questions were ruled by the founder on 2026-07-17 — rulings are binding and
recorded in §0.1. Original questions kept below for the record; where a ruling overrode
a proposal (Q1, Q4, Q5), §0.1 wins.

1. **Gate cadence for grouped rows.** docs/10 §3 groups milestones ("D2-D3", "D4-D5",
   "D8-D9"). TE-1 says gates run at the end of *each* Dn. **Proposal:** run the row's
   gates at the end of each milestone in the range (as in §2 table above).
2. **ux-reviewer / architect window conflicts.** docs/10 §1 says ux-reviewer "D7-D8
   only"; §3 schedule includes it in the D8-D9 row; its charter says D7-D9. Also the
   architect charter emits UML at D13, but the §3 D13 row lists only ops-engineer.
   **Proposal:** §3 schedule wins → ux-reviewer at D7, D8, D9; architect additionally
   runs at D13 solely to refresh docs/uml/ per its charter.
3. **prices.yaml seed + golden spreadsheet.** I will draft OpenAI + Anthropic rates from
   provider public price pages at D3 and hand-compute fixtures/pricing_golden.csv.
   **Proposal:** founder verifies the golden spreadsheet numbers before the D3 gate runs
   (money math is the product; a wrong seed table poisons every golden test downstream).
   Same review covers the D1-detector frontier list + suggested-model map at D5.
4. **Anthropic cache accounting.** Anthropic logs split cache_creation vs cache_read
   tokens; CallRecord has a single `cached_tokens` and FR-05 pricing has one `cached`
   rate. **Proposal:** `cached_tokens` = cache_READ tokens; add an optional
   `cache_write` rate per model in prices.yaml (used when present, else write tokens
   billed at input rate — conservative). Documented in methodology appendix.
5. **D2 missing-cache `delta_est` undefined** (docs/03 §3). **Proposal:** hash-based
   buckets → delta_est = 0 over the hashed prefix length (exact, confidence=conservative);
   token-count-heuristic buckets → configurable `CACHE_SUFFIX_EST_TOKENS` default 200
   subtracted from prompt_tokens, confidence=estimated.
6. **prefix_hash N** (ADR-7 "first N tokens' text"; no tokenizer in the dependency
   list). **Proposal:** SHA-256 over first `PREFIX_HASH_CHARS=4096` characters
   (≈1024 tokens at ~4 chars/token) when text present in logs.
7. **Monthly extrapolation rule.** Findings report monthly_cost_impact_usd but uploads
   cover arbitrary windows. **Proposal:** scale observed waste by `30 / observed_days`
   (observed_days = span of distinct UTC days in the frame, min 1); stated in the
   methodology appendix; no scaling cap (conservative estimators already applied).
8. **Payment ↔ audit entitlement.** FR-18 "payment before upload unlock".
   **Proposal:** one completed payment = one audit credit; free-for-testimonial audits
   = admin mark-paid with amount 0, `paid_via='comp'` (audit-logged).
9. **Signed report URL expiry** (FR-15 "expiring", duration unspecified).
   **Proposal:** `REPORT_URL_EXPIRY_DAYS=30` (config); report artifacts persist after
   the 7-day raw purge; admin can re-issue links (FR-19 download).
10. **D3 prompt-bloat "similar completion sizes"** grouping undefined. **Proposal:**
    log2 buckets on completion_tokens; route p90 prompt_tokens compared to corpus
    median within the same bucket; flag when > BLOAT_MULT (2.0) ×.
11. **Session lifetime** unspecified (magic link expiry is 15 min, session isn't).
    **Proposal:** `SESSION_TTL_DAYS=7`, sliding not renewed (simple, v1).
12. **Cron mechanism.** Runbook allows ofelia or host crontab. **Proposal:** ofelia
    sidecar in compose (single-command deploy, staging=prod parity).

---

## 5. Token-economy compliance notes (self-applied)

Context at PLAN.md authoring: ~60K tokens (docs read once, whole — mandated by kickoff;
everything else grep/targeted). Milestone hygiene per TE-9/K-3: clear at each Dn start,
carry only PLAN.md + STATUS.md + current Dn section. K-2 in force: two failed fix
attempts on one test → STOP, write state to STATUS.md, ask founder.
