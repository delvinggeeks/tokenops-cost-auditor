# PRD — TokenOps Cost Auditor (v1.0)

Product: TokenOps Cost Auditor (Phase 1 of the TokenOps cost-control platform)
Owner: Lokesh (Delving Geeks / WitAura) · Status: APPROVED-PENDING-FOUNDER-SIGNOFF
Date: 2026-07-17 · Ship target: 14 days from kickoff

## 1. Problem statement (validated)

Software companies shipping AI features cannot see or control where their LLM
API spend goes. Waste accumulates silently through oversized models on simple
tasks, missing prompt caching, bloated system prompts, retry storms, agent
loops, and unbounded max_tokens. Independent field reports (2026) put pure
waste at 40–60% of production token budgets. Discovering it requires either
(a) adopting an observability SDK/gateway (an engineering project teams
defer) or (b) hiring AI-infra expertise (~$180–250K in the US, scarce).
Result: teams discover overruns only when the monthly invoice lands.

## 2. Market validation summary (research, Jul 2026)

- Waste magnitude: operator field reports converge on 40–60% waste across
  venture-backed SaaS and enterprise platform teams.
- Urgency driver: Gartner forecasts AI services cost becoming a leading
  competitive factor in software margins by end-2026.
- Competitive shelf: Helicone, Langfuse, LiteLLM, Portkey, Bifrost, Datadog
  LLM observability = dashboards + gateways. ALL require integration
  (SDK, proxy, or gateway adoption) before insight. None deliver a
  prescriptive, dollar-ranked audit REPORT as a product.
- Emerging validation of the audit motion: consultancies (e.g. AWS partner
  Automat-it, Feb 2026) now sell LLM cost/selection audits claiming up to
  60% savings — enterprise-priced, human-delivered, slow.
- GAP (our wedge): zero-integration, upload-logs, deterministic audit with
  ranked findings and fixes, delivered in 48 hours, logs deleted after
  analysis, at self-serve pricing.

## 3. Target customer & personas

Primary: CTO / founding engineer at software companies $0.5M–$20M ARR with
$2K–$100K/month LLM API spend (OpenAI and/or Anthropic).
Secondary: engineering leads running agentic dev tooling fleets (Claude
Code / Codex) with unattributed token burn.
Tertiary (phase 2 lead-gen): agencies auditing on behalf of their clients.

Persona P1 "Spending CTO": suspects waste, no time to instrument. Wants a
number and a fix list. Buys outcome, not tooling.
Persona P2 "Agent-fleet lead": burned by runaway agent sessions (e.g. 5M
tokens on a wrong assumption). Wants loop/retry detection and budgets.

## 4. Value proposition & positioning

"Upload your LLM API logs. In 48 hours, a report showing exactly where
30–60% of your spend is wasted and how to fix it. No SDK, no proxy, no
integration. Logs analyzed then deleted."

Positioning line vs competitors: dashboards need integration and an
operator; we deliver the answer. Privacy line: process-and-delete, 7-day
auto-purge, no training on customer data.

## 5. Goals & success metrics

Business (day 45): 5 audits delivered, 2 paid, 1 retainer/Phase-2
conversation opened. Revenue signal > vanity signups.
Product (day 14): live in production; end-to-end audit (upload → PDF) on
founder's own Claude Code logs completes < 10 min for a 1M-row JSONL.
Quality: zero hallucination risk by construction (analysis engine contains
no LLM calls); every finding carries evidence rows and a $ impact figure.

## 6. Scope

IN (v1): JSONL log upload (OpenAI + Anthropic schemas, generic CSV
fallback) · deterministic rules engine (6 detectors) · versioned pricing
table · findings ranked by monthly $ impact · branded PDF + web report ·
magic-link auth · Razorpay (INR) + Stripe payment links (USD) · 7-day
raw-log auto-purge · admin panel (token-gated) · observability (structured
logs, health, error tracking, backups).

OUT (v1, explicitly): live proxy/gateway · policy engine/budgets ·
LLM-powered analysis · multi-tenant orgs/roles · SSO · SOC2 · dashboards
beyond the report page · auto-fix code changes. These are Phase 2+ and are
pulled by customer demand, not pushed.

## 7. Business model & pricing

Audit: $500 flat (₹20,000 India) per audit up to 10M calls/month volume;
first 5 audits free-for-testimonial during launch. Phase 2 upsell: managed
control plane retainer $2–6K/mo or 20–25% gain-share of verified savings.
COGS per audit ≈ compute pennies (no inference); gross margin > 95%.

## 8. Risks & mitigations

R1 Log-export friction (customer can't produce JSONL): provide exporter
scripts + generic CSV mapping docs; accept provider dashboard CSVs.
R2 "Our data is sensitive": process-and-delete policy, self-serve purge,
on-prem audit script as premium fallback (Phase 2).
R3 Incumbent feature risk (Helicone et al. add "audit report"): our moat is
zero-integration motion + operator layer + Phase 2 service wrapper.
R4 Findings disputed: every finding cites raw evidence rows; conservative
savings estimates; "verified savings" methodology documented in report.
R5 Solo-founder bandwidth: scope frozen by this PRD; changes require
written PRD amendment (see 10).

## 9. Compliance & data policy (v1 pragmatic)

Customer logs may contain prompts (sensitive). Controls: TLS in transit,
encrypted disk at rest, raw uploads purged 7 days post-report (cron +
audit-logged), no third-party data sharing, no LLM calls on customer data,
DPA-lite one-pager available. India entity invoicing; LUT filed for
zero-rated export of services (USD/Stripe path).

## 10. Change control

Any scope addition during the 14-day build is rejected by default and
parked in BACKLOG.md. Amendment requires founder-written note in this file
under "Amendments" with date + reason.

## Amendments

- 2026-07-17 R-NAMING (founder): product name "TokenOps Cost Auditor" in full across
  all dirs/files/code; spec strings updated accordingly (docs/01 FR-04 CLI name,
  docs/03 §1 tree `src/tokenops_cost_auditor/`, docs/04 coverage-rule paths,
  ux-reviewer charter path).
- 2026-07-17 R-API (founder): API hardening in scope before the D6 API surface —
  FR-25 (/api/v1 versioned routes), FR-26 (idempotent uploads), FR-27 (webhook
  timestamp tolerance + event dedup), NFR-12 (user-else-IP rate-limit keying +
  Retry-After), NFR-13 (MAX_CONCURRENT_AUDITS queue admission), NFR-14 (uniform
  JSON error envelope). API keys, queues, orgs/SSO, SOC2 remain OUT with recorded
  triggers (BACKLOG.md).
- 2026-07-17 R-PRICING-OPS (founder): NFR-15 (last_verified + CI staleness warning
  + digest age), FR-28 (report prints pricing version + unpriced models), FR-29
  (pricing_refresh.py read-only diff tooling; never writes prices.yaml). Docs-site
  presents human-verified versioned pricing as a trust feature.
- 2026-07-17 R-PRICING-AGENT (founder): WP-P1.5 pricing-watch pipeline recorded for
  post-launch week 3-4 (BACKLOG.md); NOT in D1-D14 scope. Hard rules: no
  auto-approval path in code; crawler has zero write access to prices.yaml;
  LLM-assisted extraction only into the candidate queue; disagreements flagged,
  never auto-resolved; every approval audit-logged with founder as actor.
- 2026-07-17 R-ICP (founder): primary ICP updated to agent-fleet engineering teams
  (Claude Code/Codex logs on disk) per docs/09b finding #2; log-exporter scripts are
  first-class onboarding deliverables — FR-24 added to docs/01 (Claude Code exporter,
  D2); D8 landing copy leads with the agent-fleet story; marketing stats restricted to
  attributed 79%/98% figures until dogfood numbers exist (docs/09 §6 amended).
- 2026-07-19 R-CONNECT (founder) — supersedes the WP-P2-AGG tripwire:
  (1) WP-P2-AGG PROMOTED to immediate post-polish build (est. 1-2 wks):
  "Connect OpenAI" / "Connect Anthropic" flows — customer pastes an org/admin
  API key; usage pulled server-side via the official Usage/Admin APIs; reduced
  detector set as documented since D1; key handling encrypted at rest,
  revocable, never logged; UI parity with the upload flow. (2) WP-CC-LINK (was WP-COLLECTOR; consolidated R-CC-LINK 2026-07-23)
  registered (next after AGG): pipx-installable watcher for Claude Code
  transcript dirs — dedup per UAT-D5 law, counts-only by construction,
  scheduled ship to the API (FR-26 idempotency); one command, zero code
  changes; the enterprise fleet onboarding. (3) SDK/proxy remains Phase-2
  control plane — X-01/X-02 intact for the audit product; in-path components
  live in the customer's VPC per the deployment contract, post-trust.
  (4) Sequence: R-LAUNCH-POLISH + R-ONBOARD → walkthrough → launch thread
  with Connect flows honestly absent from claims → AGG build starts
  immediately after.
- 2026-07-20 GRAND CONSOLIDATED ORDER v2 (founder): platform vision recorded
  (PLAN §0.0 — WitAura AI Agentic Engineering Governance Platform ecosystem;
  buyer = business owner; proof = verified savings; three rings strictly
  sequenced); intelligence flywheel recorded (docs/12-FLYWHEEL.md — five
  ingestion tiers T1-T5 on one CallRecordFrame/AggregateFrame contract,
  deterministic LLM-free judgment as label factory, learning ladder L0-L4
  under the honesty law, four moats, R-STANDARDS: OTel GenAI semconv ingest
  constraint + FOCUS-aligned export, docs-site Standards page). v1.5
  "MONITOR" SCOPE FROZEN, 14 working days, WP-1..7 (Connect primary
  onboarding; owner-lens dashboard R-OWNER-LENS + FR-31; proactive re-audits
  + alerts observe-and-alert-only + L0 feedback capture; Savings Statement;
  settings; Razorpay+Stripe subscriptions Free/$99 Pro/$299 Team/one-shot
  $500 kept; polish+onboard delivering R-LAUNCH-POLISH + R-ONBOARD, hero A/B
  per R-PAINMOMENT). Requirement amendments: X-05 relaxed ONLY to SSR+htmx
  for v1.5; FR-22 extended to connector-pulled and streamed data; FR-31
  added. Hard conditions: scope frozen (additions = one BACKLOG line); day
  14 ships whatever exists; founder walkthrough of the live product during
  the build; at completion launch assets refresh (figure inventory only,
  rails attached), thread posts, day-45 revenue gate restarts from that
  date. First task: PLAN-V15.md, then STOP for founder approval — no
  application code before approval.
