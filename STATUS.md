# STATUS.md — shared memory (TE-4)

One paragraph per milestone: decisions, open questions, file map delta. Gate agents
read this instead of exploring the repo.

## D1 — scaffold (complete, awaiting gate sweep G1)

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
