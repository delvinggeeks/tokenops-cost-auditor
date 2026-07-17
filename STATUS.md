# STATUS.md — shared memory (TE-4)

One paragraph per milestone: decisions, open questions, file map delta. Gate agents
read this instead of exploring the repo.

## D5 — rules part 2 (complete, all green; G3 sweep next)

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
