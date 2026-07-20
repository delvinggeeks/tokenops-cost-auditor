# docs/12 — Intelligence Flywheel (founder, 2026-07-20, GRAND CONSOLIDATED ORDER v2 Part B)

Recorded verbatim in substance. Governs sequencing of ingestion, judgment,
and learning across the WitAura AI Agentic Engineering Governance Platform
(vision: PLAN.md §0.0). TokenOps Cost Auditor is the wedge; every stage
below obeys the standing laws — FR-22 counts-only, golden discipline,
X-scope for the audit product, deployment contract for anything in-VPC.

## STAGE 1 — UNIVERSAL INGESTION

Five connector tiers, one contract: **CallRecordFrame / AggregateFrame** —
provenance + dedup stats per row; detector coverage honestly declared per
tier (reports state which detectors a tier can and cannot feed).

- **T1 FILE** — upload / CLI (shipped, v1).
- **T2 ACCOUNT** — "Connect OpenAI/Anthropic" via official Usage/Admin
  APIs (v1.5 WP-1; promoted by R-CONNECT 2026-07-19).
- **T3 COLLECTOR** — pipx transcript watcher — UAT-D5 dedup law,
  counts-only by construction (WP-COLLECTOR, post-launch).
- **T4 STREAM** — OTLP ingest endpoint speaking OpenTelemetry GenAI
  semantic conventions (gen_ai.* token-usage attributes ->
  CallRecordFrame mapping documented; dual-version attribute handling
  while the conventions are experimental; prompt-content attributes
  DROPPED AT INGEST — the FR-22 counts-only law applies at the door).
  Any customer with existing OTel instrumentation points an exporter at
  us with zero custom code. Spec after the first 3 customer
  conversations; constraint recorded now (R-STANDARDS).
  [R-AGENTIC-DIMENSIONS 1 (founder 2026-07-20): the T4 mapping spec must
  preserve agent-dimension attributes from GenAI semconv spans
  (agent/operation identity, trace linkage) so CallRecordFrame supports
  cost-per-agent / per-task / per-chain attribution; per-agent findings
  become standard report sections at T4 build time.]
  [R-RAG 1 (founder 2026-07-20): the T4 mapping spec preserves vector-DB
  query spans (GenAI semconv) so cost-per-pipeline-stage and
  per-knowledge-base attribution become report dimensions at T4 build
  time. RAG boundary: economics only — every RAG finding carries the
  quality-validation caveat.]
- **T5 GATEWAY** — in-VPC control plane (Phase 2; X-01/X-02 intact for
  the audit product; deployment contract applies).

## INTENT LAW (R-INTENT-DECLARED + R-INTENT-LADDER, founder 2026-07-22)

The platform NEVER infers developer intent from CONTENT, and NEVER takes an
optimization decision autonomously. Intent enters by DECLARATION; decisions
ship as recommendations until a human-approved policy exists (control-plane
era, X-02 path). The structural reasons are FR-22 (we never hold the text)
and NFR-01 (the engine performs no inference).

Intent is read at three levels — only the content-inferred one is banned:

- **BEHAVIORAL** — deterministic shape algorithms over counts, timing,
  models and cache fields: the detector suite, including D7. Recurring
  shapes = loops; monotonic prompt growth = context bloat; burst patterns =
  retries or flail; repeat-prefix-with-no-cache-reads = unclaimed caching.
- **DECLARED** — task tags the customer supplies: class, quality
  sensitivity, expected recurrence.
- **LEARNED** — L0 Applied/Dismissed labels feeding L2 threshold training.

Sales language: "your traffic's shape tells us what it's doing — you tell
us why — we never read what it says."

COPY LAW at depth (c): findings address the developer as the operator being
handed efficiency wins, never the party at fault — "your pipeline, same
output, lower bill." Owner depth stays money-verified. ux-reviewer checks
tone at both depths.

## STAGE 2 — DETERMINISTIC JUDGMENT

The shipped engine; LLM-free forever — it manufactures the clean
ground-truth labels Stage 3 trains on. Golden discipline non-negotiable.

## STAGE 3 — LEARNING LADDER

**HONESTY LAW: no model ships below its data threshold; every model output
prints its training-population size.**

- **L0** (n=1, BUILD NOW in v1.5): feedback capture — Applied / Dismissed /
  Not-relevant per finding + optional savings-realized field; the next
  audit auto-computes before/after deltas. The labeling pipeline; feeds
  the owner headline and the Savings Statement.
- **L1** (n>=10): peer-benchmark percentiles ("your waste = p75 of
  companies your size") — prebuilt, dormant until threshold.
- **L2** (n>=25): adaptive detector-threshold calibration trained on
  Applied/Dismissed labels; shadow-mode first.
- **L3** (n>=50 + 6mo history): predictive spend forecasts + agent-session
  anomaly detection before the invoice; alert-only.
  [R-AGENTIC-DIMENSIONS 3: anomaly detection explicitly scoped to fire
  MID-CYCLE (before the invoice); alert-only until the control-plane era.]
- **L4** (control-plane era): policy learning from cross-customer fix
  outcomes; enforcement always human-approved.
  [R-AGENTIC-DIMENSIONS 2 — control-plane policy grammar principle:
  policies are human-approved once, machine-enforced continuously, every
  enforcement action audit-logged, policy changes always human-gated.
  This is the platform's definition of "autonomous mode."]

## R-AGNOSTIC (founder, 2026-07-20) — provider/tool expansion law

Multi-provider/multi-tool expansion is pull-sequenced, never speculative:
each addition = (a) a pricing-table extension with founder-verified golden
rows, and/or (b) ONE adapter into an existing tier (T1 parser / T2
usage-API / T4 already-free / AGG seat-export). Priority order seeded:
Gemini, Bedrock, Azure-OpenAI (T2 class); Copilot admin exports (AGG
class); per-tool T1 parsers on first customer request each. Detectors,
reports, and the flywheel are provider-neutral by the frame contract —
no per-tool forks, ever.

## ZERO-TOKEN ARCHITECTURE (R-ZTA, founder 2026-07-22)

Positioning vocabulary for the engine we already ship: "deterministic
engine, no inference — we never burn your tokens to count your tokens."
Enforced by NFR-01 and the T-NFR-01 import guard, not by assertion. D6's
depth-(a) alias is "loop burn"; Build Health metrics adopt the "loop
engineering" vocabulary when they ship. Attribution: Hightower,
PlatformCon 2026 — one short quote maximum, linked, where referenced.

## FOUR MOATS (verbatim)

DATA (labels + benchmarks accumulate from customer one; clones start at
n=0 forever) · TRUTH (golden-verified pricing, published self-audit
ledger, weekly maintenance) · INTEGRATION (five tiers meeting data where
it already lives; OTel/FOCUS standards adoption) · TRUST (counts-only,
evidence rows, human gates).

## R-STANDARDS (recorded now, spec'd at T4 build)

- FOCUS-aligned export mode for report JSON + aggregates.
- OTel GenAI semantic-convention ingest per T4 above.
- docs-site Engineering section gains a "Standards" page naming OTel GenAI
  semconv + FOCUS (applied 2026-07-20).
