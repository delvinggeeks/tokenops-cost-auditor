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
- **T5 GATEWAY** — in-VPC control plane (Phase 2; X-01/X-02 intact for
  the audit product; deployment contract applies).

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
- **L4** (control-plane era): policy learning from cross-customer fix
  outcomes; enforcement always human-approved.

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
