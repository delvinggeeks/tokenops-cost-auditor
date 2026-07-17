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
- 2026-07-17 R-ICP (founder): primary ICP updated to agent-fleet engineering teams
  (Claude Code/Codex logs on disk) per docs/09b finding #2; log-exporter scripts are
  first-class onboarding deliverables — FR-24 added to docs/01 (Claude Code exporter,
  D2); D8 landing copy leads with the agent-fleet story; marketing stats restricted to
  attributed 79%/98% figures until dogfood numbers exist (docs/09 §6 amended).
