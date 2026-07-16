# Roadmap — TokenOps

## Phase 1: Cost Auditor — 14-day build (parallel sales track mandatory)

D1  Scaffold FROM SCRATCH in an empty repo (no templates, no
    boilerplates): uv project, src layout per LLD, docker-compose,
    CI, CLAUDE.md rules file. CI pipeline green on empty suite.
D2  Ingest: parsers + normalizer + validator + fixtures F1–F4. Tests.
D3  Pricing: table + coster + golden spreadsheet + property test.
D4  Rules: D2 missing-cache, D4 retry-storm (highest-signal detectors
    first) + waste_pack fixture v1. Tests.
D5  Rules: D1 oversized, D3 bloat, D6 chatty-loop, D5 unbounded. Golden
    numbers complete. NFR-01 import guard.
D6  Runner end-to-end; call_aggregates; report JSON; status API.
D7  PDF + web report + signer; report visual pass (weasyprint styling).
D8  Auth (magic link) + landing page (copy from PRD §4, FR-23 string) +
    ToS/Privacy/DPA-lite pages.
D9  Payments (Razorpay link + webhook; Stripe env-gated) + admin panel.
D10 Lifecycle purge + audit_log + daily digest + backup script. Ops
    drills on staging (Oracle box).
D11 UAT-1: dogfood on founder's Claude Code logs. Fix findings quality.
    Screenshot material for content.
D12 UAT-2: first external free audit (design partner). Export docs
    hardened. Perf test on 1M fixture.
D13 Production VPS deploy per RUNBOOK §2. Smoke. UptimeRobot. Payment
    links live.
D14 Launch: build-in-public thread (dogfood numbers), landing live,
    first paid link sent.

SALES TRACK (runs from D3, non-negotiable):
D3  announce build-in-public thread #1; DM list of 30 CTOs drafted.
D5  10 DMs sent (offer: first 5 audits free-for-testimonial).
D8  10 more DMs; post thread #2 (detector deep-dive).
D11 dogfood-results thread #3 (real numbers) — the credibility asset.
D14 launch post; book 5 audits week 3.
Day-45 kill/pivot gate (from PRD §5): 5 delivered, 2 paid, else pivot
review per idea-table runner-up.

## Phase 2 (pull-driven; start only on customer demand signal)

P2-A Control plane: LiteLLM-based VPC deploy + policy engine (routing
     rules, cache enforcement, per-team/agent budgets, hard stops) —
     reuses pricing + rules packages per HLD §7.
P2-B Retainer productization: monthly optimization report automation;
     model-release regression module (idea #3 as feature).
P2-C Agentic dev-tool guardrails skin (Claude Code/Codex fleets):
     per-task budgets, loop kill-switch, cost-per-merged-PR.
P2-D Subscriptions billing, org/RBAC, SSO as enterprise pull dictates.

## Backlog (parked; PRD change control applies)

Proxy live-capture mode · LLM-written narrative summaries (X-04 until
demand + guardrails) · marketplace listings (AWS/DO) · partner/agency
white-label reports · SOC2 track.
