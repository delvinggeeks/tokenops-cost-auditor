# Market Research Refresh — TokenOps Cost Auditor (2026-07-17)

Founder-requested re-run of docs/09 before build start. Method: 5-angle web-search
fan-out → 21 sources fetched → 104 claims extracted → top 25 adversarially verified
(3 independent votes each; ≥2 refute kills) → 21 confirmed, 4 refuted. Synthesis and
recommendations authored in the main build thread. Every claim below is labeled
VERIFIED (survived 3-vote adversarial check, quote-backed) or UNVERIFIED/REFUTED.
Recommendations are in §5 and are recommendations only — PRD amendments remain
founder-written (PRD §10).

## 1. Competitive shelf check — wedge still open, with two new neighbors

- VERIFIED (3-0): **No zero-integration, upload-logs, fixed-price LLM waste audit
  product found.** Closest audit-shaped offering: ActiveWizards sells a productized
  "LLM Cost Audit" (written report, ranked optimizations) but with NO published price,
  NO turnaround commitment, intake gated by manual spec review — the opaque consultancy
  motion docs/09 described, not our wedge.
  [activewizards.com/services/llm-cost-audit]
- VERIFIED (3-0): **Helicone was acquired by Mintlify (announced 2026-03-03) and its
  product is in maintenance mode** — a named incumbent is out of the feature race.
  Incumbent-feature risk (PRD R3) is DOWN vs the docs/09 baseline.
  [helicone.ai/blog/joining-mintlify]
- VERIFIED (2-1): Datadog LLM Observability cost tracking still requires SDK/span
  instrumentation; its cost monitoring is passive dashboards — no prescriptive audit
  report feature documented. [docs.datadoghq.com/llm_observability/monitoring/cost]
- VERIFIED (3-0): **Vaudit** (new, ~Jun 2026) sells AI *billing-error* audits — claims
  $34M invoices reviewed across 60 companies Mar–Jun 2026, ~$1.7M (~5%) overcharges
  found. It hunts provider billing errors, NOT customer-side token waste — adjacent,
  not overlapping; its traction validates the "audit AI spend" buying motion.
  [techstartups.com 2026-06-25] (Its pricing model: claim REFUTED 0-3 — do not cite.)
- VERIFIED (3-0): OpenAI (Jun 2026) and Anthropic (Aug 2025) shipped native enterprise
  spend analytics/limits — descriptive visibility is commoditizing at the provider
  layer; prescriptive dollar-ranked findings remain un-shipped there. [cnbc.com]

## 2. docs/09 claim verification — corrections required in marketing copy

| docs/09 stat | Verdict | Correction |
|---|---|---|
| "79% overran AI budgets" | VERIFIED (3-0) with caveat | Real (DoiT/Sapio, Feb 2026, n=500) but population = finance leaders at 1,000+-employee US/UK orgs — NOT our $2K–$100K/mo ICP. Cite with attribution, never as ICP evidence. |
| "even mature FinOps teams overspent 31%" | VERIFIED (3-0) | 30.9% mean overspend, worst segment of same survey. Usable. |
| "73% blew AI budget plans" | UNSUPPORTED | Not in State of FinOps 2026 or the DoiT survey. Traces (via a blog) to an unattributed "review of 127 implementations". **Drop from copy** until a primary source exists. |
| "98% of FinOps teams manage AI spend" | VERIFIED (3-0) with caveat | Confirmed (State of FinOps 2026; up from 31% two years ago). Denominator = self-selected FinOps practitioners, not all software companies. |
| "40–60% of token spend is waste" | **UNVERIFIED** | No primary source found. Circulates verbatim in unattributed blog posts (one rated unreliable). Keep ONLY as "operator field reports" framing — better: replace with our own dogfood/audit numbers after D11. A supporting "95% run frontier models" quote was REFUTED (0-3). |

A product whose pitch is "zero hallucination, every finding evidence-cited" must hold
its own marketing to the same bar — the corrections above are a credibility asset.

## 3. Log-export feasibility (risk R1) — CONFIRMED as the #1 product risk

- VERIFIED (3-0): **OpenAI's Usage API returns time-bucketed aggregates (1m/1h/1d),
  not per-request logs** — but DOES expose `input_cached_tokens` alongside
  input/output tokens and request counts. [developers.openai.com cookbook]
- VERIFIED (3-0): **Anthropic's Usage API is likewise bucketed (1m/1h/1d)**, reports
  uncached/cached/cache-creation/output tokens separately, but **requires an org-level
  Admin API key** (unavailable to individual accounts; endpoints unavailable for
  Claude on AWS). Console exports are CSV aggregates by model/date/API-key.
  [platform.claude.com docs; support.anthropic.com]
- Net: **neither provider natively exports per-request logs.** Customers who can
  upload FR-01-shaped JSONL are those who already log LLM calls in their own app/
  gateway/agent tooling. The PRD R1 mitigation (exporter scripts + generic CSV docs)
  is not a nice-to-have — it is the onboarding product.

## 4. Pricing / WTP — thin verified signal

Verified evidence on one-off-audit WTP in this exact segment is weak. Directional
only: productized fixed-price async audits exist as a category (an unverified comp:
$350/48h landing-page audit with 850+ sales); Vaudit's rapid enterprise traction
verifies budget exists for "audit my AI spend". Nothing verified says $500 is wrong
in either direction. Keep $500/₹20,000; revisit at the day-45 gate with real
conversion data.

## 5. RECOMMENDATIONS (clearly marked; founder decides)

1. **Lead onboarding with log sources that exist today**: agentic dev-tool fleets
   (Claude Code/Codex logs are local files — persona P2), teams already logging LLM
   calls app-side, gateway/proxy log owners. The D11 dogfood on Claude Code logs is
   also the highest-feasibility ICP demo — publish it as the launch asset.
2. **Detector emphasis in copy: D2 missing-cache first.** Cached-token fields are the
   one waste signal BOTH providers verifiably expose even in aggregate exports; cache
   waste findings are also the easiest for a CTO to verify independently. D4/D6
   (retries/loops) need per-request logs — frame them as the "deep audit" tier that
   rewards better logs.
3. **Positioning line adjustment** (PRD §4 candidate, founder to amend): "Dashboards
   show you spend. We hand you the ranked list of what to fix — from the logs you
   already have. No SDK, no proxy, analyzed then deleted." Explicitly differentiate
   vs Vaudit: "we find waste you control, not billing errors."
4. **Marketing copy hygiene** per §2: drop "73%", caveat "79%"/"98%", replace
   "40–60%" with dogfood-derived numbers after D11 (docs/09 §6 needs a founder edit).
5. **Scope-adjacent idea parked to BACKLOG.md** (PRD §10): "aggregate-mode audit"
   accepting provider Usage-API/console exports (bucketed, no per-request rows) with
   a reduced detector set (D2 + model-mix). Would widen the funnel to customers with
   zero request logging — but it is NOT in the frozen v1 scope.
6. **Speed matters more than feared, in a good way**: with Helicone parked and
   providers shipping only descriptive dashboards, the prescriptive-audit window is
   open. No change to the 14-day plan.

## Sources (21 fetched; quality-tagged)

Primary: activewizards.com, helicone.ai, docs.datadoghq.com, doit.com,
data.finops.org, linuxfoundation.org, developers.openai.com,
platform.claude.com, support.anthropic.com. Secondary: techstartups.com, cnbc.com.
Forum: news.ycombinator.com, community.openai.com. Blog (low confidence): dev.to (×3),
beri.net, pub.towardsai.net, abhs.in, wayfront.com. Unreliable: editorialge.com.
