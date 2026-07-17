# STATUS.md — shared memory (TE-4)

One paragraph per milestone: decisions, open questions, file map delta. Gate agents
read this instead of exploring the repo.

## D-DOCS — docs site built (gates next)

Branch `d-docs`. MkDocs + Material (dev-only dep per DOCS-PLAN §1), 27 pages
per approved page tree, mkdocs.yml strict + local palette (no CDNs/fonts/
trackers), pymdownx snippets transclude docs/04 (traceability page) and
docs/uml/*.mmd (architecture page). scripts/export_openapi.py generates
api/endpoints.md from the app factory; --check drift gate + `mkdocs build
--strict` + artifact upload added as CI `docs` job. docs/04 gained the DOC
column (same commit as pages). MP register at build: RESOLVED with real repo
numbers — MP-3 (20 endpoints generated), MP-5 (G4 UML embedded), MP-7
(determinism via T-REP-03/08), MP-8+MP-10 (all six golden rows: D1 $1.35,
D2 $0.246784, D3 $0.50, D4 $0.0510, D5 $0.00 informational, D6 $0.096),
MP-9 (legal single-sourcing: web templates authoritative, docs mirror,
drift-failing sync tests in tests/test_docs_site.py — clause structure +
FR-23 + price). STILL PENDING (greppable MEASUREMENT-PENDING blocks):
MP-1 e2e timing claim, MP-2 report screenshot, MP-6 perf numbers (founder
precondition: ≥1 successful nightly perf run; none exists yet). Stats
policy test-enforced (attributed 79/31/98 only; 40-60/73 banned). Suite
177 passed + 1 CI skip; strict build zero warnings.

## D10 — G6 SWEEP COMPLETE (ops-engineer PASS-WITH-NOTES, vv PASS-WITH-NOTES)

G6 verdicts. ops-engineer: PASS-WITH-NOTES — container_name/ofelia targets match,
mounts correct, compose valid, no postgres ports, FR-29 status-file paths agree,
Dockerfile chown covers scripts/. Notes FIXED same-day: runbook §4 reworded
(tar snapshot, not rsync — postgres image ships none), digest disk check now
samples uploads AND backups filesystems (deduped). vv: PASS-WITH-NOTES —
171 passed + 1 CI skip reproduced; coverage 93.7%/100%/100% (aggregate gate);
T-LIF value-asserting incl. due-vs-not-due discrimination; T-OPS-04 byte-identical
never-write assertion confirmed; no money-math files touched. Notes: stale fixture
comment FIXED; purge.py main() CLI lines uncovered (78.4% file-level, acceptable —
CLI exercised by ops drills; revisit only if per-file gates tighten). Restore
drill evidence accepted (runbook §4 log). Merged to main; tag d10.

Branch `d10-lifecycle-ops`. R-TOOLCHAIN recorded first (TE-11 in docs/10 §2 +
CLAUDE.md verbatim copy + all six charters). lifecycle/purge.py (FR-21): due =
report_ready_at + PURGE_AFTER_DAYS, created_at fallback for failed/never-rendered
audits (decision: FR-23 "nothing retained beyond 7 days" must hold on failure
paths); removes upload dir only, keeps reports+aggregates; audit_log actor
system@purge {"mode":"scheduled"}; module CLI for ofelia. scripts/backup.sh
(NFR-08): runs INSIDE postgres container (ofelia job-exec), pg_dump -Fc
write-then-rename (no partials in freshness check), 14d rotation, reports
snapshot (rsync-or-tar fallback), env-gated rclone offsite. ofelia.ini jobs
wired: purge 02:00, backup 02:30, digest 03:00 UTC; compose pins
container_name for both job targets, new backups volume (rw postgres, ro app),
scripts+reports mounted ro into postgres; Dockerfile now COPYs scripts/.
scripts/daily_digest.py (runbook §3): audits/failures/revenue/purges 24h +
ALERTS (backup>26h or absent, disk>80%, pricing age NFR-15, refresh failures
FR-29, failed audits); DIGEST_TO+BACKUP_DIR added to config+.env.example;
SmtpMailAdapter.send_digest. scripts/pricing_refresh.py (FR-29): read-only —
parses # source_url comments, heuristic candidate extraction, diff output
(new ids / VERIFY-BY-HAND mismatches / unreachable); NEVER writes prices.yaml;
status JSON to <report_dir>/.ops/pricing_refresh.json consumed by digest.
Tests: T-LIF-01..03 (5), T-OPS-04 + digest (6); suite 171 passed + 1 CI skip;
mypy/ruff clean. RESTORE DRILL T-OPS-01/02 EXECUTED with real postgres:17
containers — logged in runbook §4 (88s, PASS, identical row counts, new smoke
audit on restored db). Traceability rows for FR-21/29, NFR-08/15 pre-existed.

## D8-D9 — G5 SWEEP COMPLETE (ux PASS-WITH-NOTES, cold FAIL→fixed→PASS-WITH-NOTES, spec-guard PASS-WITH-NOTES)

G5 verdicts. ux-reviewer: PASS-WITH-NOTES — notes fixed same-day (jargon glossed,
founder-approved differentiation line verbatim). cold-reviewer: FAIL with 5 findings,
all remediated in 488b40c with regression pins — (1) credit double-spend race →
claim_credit atomic UPDATE-where-unclaimed loop; (2) same-second magic-link lockout →
float-epoch iat; (3) webhook parse exceptions 500 → try/except → None/"ignored";
(4) admin actor honors X-Forwarded-For behind Caddy; (5) mark-paid rejects negative
amounts. Re-run initially re-FAILed claiming `except A, B, C:` is a SyntaxError —
WITHDRAWN as false positive: reviewer's ast.parse ran under pyenv 3.13; project pins
Python 3.14 everywhere (pyproject/.python-version/Dockerfile/CI) where PEP 758 makes
unparenthesized multi-except legal, and ruff format (py314) ENFORCES that style
(reverts parenthesization). Verified under uv 3.14.5: py_compile OK, mypy 65 files
clean, ruff clean. spec-guard: PASS-WITH-NOTES — FR-19 "download report" admin action
was missing; ADDED (GET /admin/audits/{id}/report, PDF, audit-logged, T-ADM-05,
traceability + test-plan updated, 1a7d882). Final: 160 passed + 1 CI-only skip.
Merged to main; tags d8, d9.

Branch `d8-d9-auth-payments`. D8: web/auth.py (magic tokens 15-min + sessions;
SINGLE-USE via users.last_login_at — any earlier link dies on login, no
consumed-token table), web/routes_auth.py (request/verify/logout; enumeration-
safe response; 5/min limit), session cookie HttpOnly/Secure/SameSite=Lax
(TTL Q11); api current_user now cookie-FIRST with X-User-Email as NON-PROD shim;
templates base/landing/upload + legal/{terms,privacy,dpa} (FR-23 verbatim on
landing+privacy+footer; ONE primary CTA; R-ICP agent-fleet headline; approved
79%/98% stats only; auto-router differentiation line); mail/smtp.py env-gated
(STARTTLS; APP_BASE_URL added to config for absolute links). NFR-11 BUG FOUND+
FIXED: naive sqlite datetimes interpreted as local time in epoch math — now
normalized to UTC by contract. D9: payments/{base,razorpay_link,stripe_link}
(stdlib HMAC only; FR-27 razorpay tolerance via payload created_at — documented,
signature carries no timestamp; stripe via t= param), api/routes_webhooks
(/api/v1/webhooks/*; order: signature→tolerance→append-only webhook_events
dedup→credit), FR-18 ENFORCED: one paid credit consumed per audit atomically,
402 + payment links otherwise (Q8 comp = provider comp/amount 0);
web/routes_admin (X-Admin-Token constant-time, 404 when unset, IP-logged actor,
list/rerun/purge/mark-paid, all audit-logged). Migration 002 additive (payments,
webhook_events, users.last_login_at). Architect G4 note DONE: repo-pattern
helpers (create_audit/get_user_audit) — routes no longer touch ORM directly.
Tests: T-AUTH-01..04, T-WEB-01, T-MAIL-01, T-PAY-01..07 (independent HMAC
fixtures per R-PAY), T-ADM-01..05; existing API tests updated for credit
enforcement. Suite green; coverage 94.4%/100%/100%.

## D6-D7 — G4 SWEEP COMPLETE (architect PASS-WITH-NOTES + UML, vv PASS, ux PASS-WITH-NOTES)

architect: placement per LLD §1 clean; layering verified (ReportModel sole money
assembly; renderers serialize only); ADR-1/2/3/4/5 conform; two disclosed
founder-authorized deviations accepted; docs/uml/{components,audit-seq}.mmd
EMITTED from the D6-D7 implementation (no D7-vs-D6 boundary change). Notes:
repo-pattern applied inconsistently in routes_upload (tighten at D8 refactor);
bar-width percentages are presentational only. vv: 127 passed + 1 designed skip,
coverage 94.5%/100%/100%, no money-math files touched, envelope/idempotency/
queue/signer tests all value-asserting; nit (pandas import placement) fixed.
ux: headline savings in first view, charts titled+labeled, page-breaks, fluid
layout all PASS; notes FIXED same-day: "normalized" label replaced with plain
"scaled to 30 days" wording, #N-by-impact rank badges added to waterfall and
finding cards. Merged to main; tags d6, d7. D-DOCS unblocked per R-SEQ-D6D7.

## D6-D7 — runner + reports complete

Branch `d6-d7-runner-report`. D6 file map: persistence/{models,repo}.py + alembic
migration 001 (six tables incl. idempotency_keys per FR-26; additive-only),
services/runner.py (queued→processing→done|failed, NFR-13 slot admission,
idempotent re-run, user-safe failures, audit_log events), services/report/
{model,render_json}.py (ReportModel assembled ONCE — render layers never
recompute; deterministic JSON; FR-28 pricing provenance; methodology carries
C3 floors + R-Q4/R-Q5 haircuts + R-D1-MAP caveat), lifecycle/auditlog.py
(INSERT-only), mail/base.py (port + log adapter), api/routes_upload.py
(/api/v1 per FR-25; streaming 200MB cap; Idempotency-Key 201/200 per FR-26;
queue position per NFR-13; pre-D8 auth stub X-User-Email non-prod only +
pre-D9 payment-gate stub, both behind dependencies), NFR-12 user-else-IP
limiter keying w/ Retry-After, NFR-14 envelope on all /api/* errors.
D7 file map: report/signer.py (30-day signed URLs), report/render_pdf.py
(weasyprint; render_report_html shared), web/templates/{_report_body,
_report_style,report,pdf/report}.html (single shared body — web and PDF cannot
diverge; headline savings number first; findings ranked; CSS bar charts with
titles/labels; evidence tables counts-only; page-break rules), web/
routes_report.py (GET /r/{token} + /r/{token}/pdf; NOT under /api/v1),
cli.py + console script `tokenops-cost-auditor` (FR-04; offline pipeline,
exit 0/2/3). Deps: python-multipart (approved). CI: weasyprint system libs in
test job. LLD §5 deviation note for architect: API paths carry /api/v1 prefix
per FR-25 founder amendment (docs/03 §5 predates R-API). Runner renders
JSON+HTML+PDF, mails signed /r/ link. Tests incl. T-API-01..07, T-NFR-03/12,
T-REP-01..08, T-LIF-04, T-NFR-11, T-CLI-01, postgres L2 (CI), determinism
repeat-render. Dogfood path for UAT-1 ready: exporter → CLI → PDF (no auth
needed) or API with stub header.

## D4-D5 — G3 SWEEP COMPLETE (vv PASS, spec-guard PASS, cold-reviewer PASS-WITH-NOTES)

vv-engineer: 86 tests green, all 15 in-scope T-RUL/T-NFR IDs non-trivial, money-math
discipline satisfied, coverage 94.1% / 100% / 100% — no notes. spec-guard: every
change maps to FR-07..13/NFR-01, X-02 observe-only confirmed (no enforcement
anywhere), FR-22 clean (EvidenceRef counts-only, fixed-vocabulary notes), fix_text
deterministic templates (X-04-consistent). cold-reviewer: 5 findings, ALL FIXED
same-day (commit ca5aed6): (1) D2 buckets spanning a pricing effective-date
boundary now reprice per row/day — regression test with independent expected
1.55136 across the Sonnet-5 Sep-1 boundary; (2) D4 mixed priced/unpriced clusters
count priced rows only (conservative); (3) D6 mixed-model runs priced at run-min
input rate (order-independent); (4) tz-naive timestamps assumed UTC defensively;
(5) '-2' suffix rule commented. Merged to main; tags d4, d5.

## D5 — rules part 2 (complete, all green)

Branch `d4-d5-detectors`. File map: services/rules/{d1_oversized_model,
d3_prompt_bloat,d5_unbounded_max_tokens,d6_chatty_loop}.py; registry now runs
D1..D6 in order; tests/test_import_guard.py (T-NFR-01, AST-based, self-testing);
waste_pack v2 (147 anthropic + 17 openai lines, 6 engineered blocks + filler).
Golden verdicts on waste_pack v2 — EXACTLY one finding per detector, all matching
independent Decimal derivations (NOTES waste_pack v2 section): D1 1.35 / D2
0.246784 (unchanged) / D3 0.50 / D4 0.0510 (unchanged) / D5 0.00 informational /
D6 0.096; clean_optimal = zero findings across all six. R-D1-MAP implemented
fully: config-seeded frontier map (dated comments), one-tier/same-provider,
re-price-at-suggested-card savings, QUALITY_CAVEAT verbatim in every D1 finding,
unmapped-frontier -> D1-INFO informational. NEW money-math defaults recorded in
NOTES (D3 excess definition, D6 overhead=run-median prompt, D1 repricing
equivalence). BEHAVIOR CHANGE flagged for gates: model-key matching in pricing
table + D1 map tightened to exact-or-dated-suffix boundary rule (prevents
gpt-5.4-nano taking gpt-5.4's card; G12 golden still exact). New config knobs:
D5_MAX_RATIO, D6_SMALL_COMPLETION_T/RUN_WINDOW_S/SESSION_GAP_S/REREAD_MIN,
D1 map seeds (.env.example updated, completeness test green). Boundary tests:
p50 149/150, bloat 2.0x edge, D5 4x edge + absent max, LOOP_MIN 7/8, session-gap
split, sibling-bleed guard, cached-bucket exclusion.

## D4 — rules part 1 (complete, all green; G3 fires at end of D5)

Branch `d4-d5-detectors`. File map: services/rules/{findings,base,registry,
d2_missing_cache,d4_retry_storm}.py; fixtures waste_pack_anthropic.jsonl +
waste_pack_openai.jsonl (split per-file format detection; tests concat) +
clean_optimal.jsonl; tests/test_rules.py (19 tests: T-RUL-00, T-RUL-EV-01,
T-RUL-D2-01..03, T-RUL-D4-01..02). Golden derivations in pricing_golden_NOTES.md
(waste_pack v1 section): D2 monthly 0.246784 (13 TTL windows/17 reads/cacheable
1024), D4 monthly 0.0510 — both independently Decimal-computed; the independent
calc CAUGHT a real bug (pandas 3.0 datetime64[us] broke nanosecond-based window
math; fixed with Timedelta division). Decisions: one Finding per D2 bucket / per
D4 identity group; D2 severity impact-scaled (high>=500,med>=50 — in NOTES), D4
severity per LLD cluster>=10 rule; hash-verified cacheable capped at
PREFIX_HASH_CHARS//4 tokens; R-Q4 0.7-haircut branch implemented + tested via
window-estimation failure injection; TTL per provider-family wired (C4 consumer
now exists — closes G2 re-run note 2/4). clean_optimal engineered to stay silent
through D5 detectors too. rules_disabled config added (T-RUL-00). D5 next: D1/D3/
D5/D6 detectors, waste_pack v2, T-NFR-01 import guard; then gate sweep G3.

## D2-D3 — G2 SWEEP COMPLETE (vv-engineer PASS-WITH-NOTES, cold-reviewer PASS-WITH-NOTES)

Founder verified golden CSV 2026-07-17 (log in pricing_golden_NOTES.md), then G2 ran.
vv: suite green, coverage 94.1%→94.5% services / 100% coster.py, golden discipline
satisfied; note was a stale STATUS header (fixed here). cold-reviewer: money math
verified against all 12 golden rows; 4 non-blocking findings, ALL FIXED in main
thread same-day with regression tests (TestG2ReviewFindings): (1) present-but-invalid
cached/cache_write_tokens now a row error, never silent 0; (2) anthropic parser
accepts integral-float usage counts, rejects garbage via prompt_tokens invalidation;
(3) generic CSV blank provider value = row error, not silent "generic" default;
(4) reconcile() docstring now states exactly what it does/doesn't validate.
Merged to main; tags d2, d3.

## D3 — pricing (complete; founder-verified)

Branch `d2-d3-ingest-pricing`. File map: services/pricing/{table.py,coster.py,
data/prices.yaml}, tests/test_pricing.py, tests/fixtures/pricing_golden.csv +
pricing_golden_NOTES.md. prices.yaml seeded from OFFICIAL pages fetched 2026-07-17
(Anthropic pricing page incl. exact cache write/read columns; OpenAI
developers.openai.com pricing) with effective_from + source_url per R-Q3; four rates
per R-Q4 (cache_write = 5-min-TTL rate; OpenAI cache_write defaults to input = zero
write premium). Sonnet-5 intro→standard boundary (2026-08-31/09-01) encoded and
boundary-tested. Coster: unified total-prompt semantics, negative-uncached clipped,
unknown model → NaN + unpriced list (audit continues). reconcile(frame, total)
verifies persisted headline total vs by-model/by-day parts ±0.5% (NFR-07); property
test (hypothesis, 200 examples). Golden values computed INDEPENDENTLY (Decimal
arithmetic, generator preserved in NOTES). Coverage: coster.py 100%, services 94.1%.
Fixtures regenerated with officially-priced OpenAI IDs (gpt-5.6-terra/5.4-mini/
5.4-nano — original invented IDs had no published rates). Money-math defaults
recorded in NOTES per R-Q6..12(a). D2_TTL_WINDOW_S=300 matches 5-min cache_write
choice. Per founder ruling: G2 (vv-engineer, cold-reviewer) runs ONLY AFTER founder
hand-verifies 8-10 golden rows.

## D2 — ingest (complete, all green)

Branch `d2-d3-ingest-pricing`. File map: services/ingest/{base,openai_jsonl,
anthropic_jsonl,generic_csv,normalizer,validator,__init__}.py;
scripts/exporters/claude_code_export.py (FR-24, R-ICP); fixtures F1-F4 + Claude Code
session fixture + seeded generator. Decisions: per-file format detection (mixed-
provider JSONL = format error, F3 is single-provider with mixed error KINDS);
CallRecordFrame gains cache_write_tokens column (R-Q4; documented LLD §2 deviation —
architect gate note for G4); unified prompt_tokens = TOTAL input semantics
(OpenAI includes cached; Anthropic input+read+write summed); prefix_hash in-memory
only, text keys stripped from raw_extra (FR-22); request_id synthesized r{line_no}
when absent. Exporter emits Anthropic-shaped JSONL, counts only, sessionId as tag,
endpoint "claude-code"; T-EXP-02 asserts no text survives. 28 tests (T-ING-01..09,
T-EXP-01..02) green.

## D1 — scaffold (COMPLETE; G1 verdicts: ops-engineer PASS, spec-guard PASS-WITH-NOTES)

G1 notes (non-blocking): re-diff .env.example vs config.py directly at D6; config.py
pre-declares FR-18/FR-20/detector settings ahead of owning milestones (intentional —
kickoff requires .env.example to cover every docs/03 §7 variable from D1).


Scaffold from scratch per PLAN.md WP-D1 on branch `d1-scaffold`. Python 3.14 (wheel +
install verification in PLAN.md §0.2). Founder ruling R-NAMING applied mid-milestone:
full product name everywhere — package is `src/tokenops_cost_auditor/` (not
`src/tokenops/`), distribution `tokenops-cost-auditor`, DB/user/container names
likewise; path strings in docs/01 (FR-04 CLI name), docs/03 §1 tree, docs/04 coverage
rule, and the ux-reviewer charter were updated to match — founder to re-confirm at D1
stop. File map: config.py, main.py (app factory, request-id middleware, /healthz with
db+disk checks), obs/{logging,errors,ratelimit}.py, persistence/{models,repo}.py +
alembic (no tables yet, additive-only), package skeleton per LLD §1, Dockerfile,
docker-compose.yml (caddy→app→postgres:17 + ofelia sidecar, postgres internal-only,
log rotation), Caddyfile, ofelia.ini (jobs commented until D10), .env.example
(complete vs config.py, test-enforced), .github/workflows/ci.yml (lint→type→test w/
postgres service→coverage gate→build; perf nightly-only; deploy manual),
scripts/coverage_gate.py, tests (T-OBS-01..03 + env-completeness; 6 passed; ruff,
mypy clean; compose config valid). Decisions: sentry-sdk NOT a dependency — NFR-06 hook
is env-gated lazy import; httpx added DEV-ONLY for TestClient (docs/05 L3). Open
questions for founder: (1) approve `pyyaml` dependency at D3 (FR-05 YAML table, no
stdlib parser) and `python-multipart` at D6 (FastAPI multipart upload); (2) confirm
doc-string updates made under R-NAMING; (3) R-Q1 nuance — UML emission lands at the
D6-D7 group gate (end of D7). Market-research refresh running; report to
docs/09b-MARKET-RESEARCH-REFRESH.md.
