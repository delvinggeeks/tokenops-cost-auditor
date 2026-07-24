# PLAN-TAAS.md — "LLM tokenomics as a service, in any environment" (founder order 2026-07-23)

Status: **APPROVED — R-PROCEED (founder, 2026-07-23), recorded in docs/00
Amendments.** §4 answers: Q1 yes (Azure→Bedrock→Gemini order), Q2 yes
(spec now, endpoint later), Q3 yes, Q4 yes (next landing touch), Q5 keep
the trigger. Sequencing per §3 unchanged.
Order source (founder, 2026-07-23, verbatim in substance): "most
enterprises use cloud AI services deployed in cloud infra — how can our
platform sit there? where are other accounts — lovable, cursor, copilot?
currently it looks standalone; we need llm tokenomics as a service,
deployable and usable in any kind of environment."
Governing docs: docs/00-07, 11, 12; BACKLOG trigger register;
R-DEPLOYMENT-CONTRACT; R-AGNOSTIC.

## 0. The honest map — most of this order EXISTS in the record as triggers

| Founder ask | Where it lives today | Status |
|---|---|---|
| "Sit inside cloud infra" | **T4 STREAM** (docs/12): an OTLP endpoint speaking OTel GenAI semconv — any app already instrumented with OpenTelemetry points an exporter at us, zero custom code; k8s attribution comes free from resource attributes (BACKLOG design note: per-team tokenomics is a GROUP BY) | Constraint recorded (R-STANDARDS); spec gated on "first 3 customer conversations" |
| "Deployed in any environment" | **R-DEPLOYMENT-CONTRACT**: single artifact, zero egress, BYO postgres/TLS/identity, air-gap bundles; ladder compose→Helm→marketplace IaC | Law in force; Helm + marketplace are registered triggers (first VPC customer / second enterprise deal) |
| "Cloud AI services" (Bedrock/Azure OpenAI/Vertex) | **R-AGNOSTIC queue**, seeded order: Gemini, Bedrock, Azure-OpenAI as T2-class connectors, each = ONE adapter + founder-verified golden pricing rows | Registered, pull-sequenced — **this order is the pull** (§2) |
| Copilot | **WP-P2-AGG** seat/credit governance via Copilot admin exports (AGG class) | Registered; same pull |
| Cursor, Lovable | BACKLOG (R-AGNOSTIC addition, 2026-07-27): candidate adapters **blocked by fact, not choice — neither exposes a public usage/billing API**. Usage from these tools on customer-owned provider keys is ALREADY captured by the shipped T2 connectors | Trigger: (first customer request) AND (an export/API existing) |
| "Front gate in their infra" | T5 GATEWAY / control plane, in-VPC | Firing condition registered (first enterprise in-VPC procurement demand) |
| Self-hosted models (vLLM/TGI) | BACKLOG design note: Prometheus token counters + GPU-hour rate card | Trigger: first self-hosted customer |

Standalone is a look, not the architecture: the five-tier ingestion design
(docs/12) was built for exactly this order. What is genuinely missing is
(a) the cloud-provider connectors nobody has pulled until now, and (b) the
T4 endpoint that makes "point your existing telemetry at us" true.

## 1. What "intelligent design to sit and do our work" means concretely

The platform never asks an enterprise to change how it runs AI. It meets
usage where it already is, in order of least intrusion:
1. **They have OTel** (most cloud-native shops): T4 OTLP ingest — no SDK,
   no proxy, no code. The counts-only law applies at the door (FR-22:
   prompt-content attributes dropped at ingest).
2. **They have a cloud AI bill**: T2 connectors pull the provider's own
   usage APIs (today OpenAI/Anthropic; §2 adds Azure OpenAI, Bedrock,
   Gemini/Vertex).
3. **They have seat tools** (Copilot): AGG-tier seat/credit exports.
4. **They have agent fleets on laptops/CI** (Claude Code today; Cursor
   when it exposes data): T3 collector (WP-CC-LINK, ruled next in queue).
5. **They have nothing standard**: T1 file upload + documented exporters —
   the universal fallback that already ships.
Every tier lands on the SAME CallRecordFrame/AggregateFrame contract, so
detectors, reports, explorer, flywheel are tier-blind by construction.

## 2. Proposed promotions (this order = the pull the register waited for)

**WP-CLOUD-T2 — cloud-provider connectors (est. 4-6 days, one per slice):**
- C-A **Azure OpenAI** (enterprise default): usage/deployments API adapter
  → AggregateFrame; pricing rows w/ golden derivations; wizard entry.
- C-B **AWS Bedrock**: CloudWatch/Cost-Explorer-based usage adapter (per
  model-id invocation + token metrics); same laws.
- C-C **Google Gemini / Vertex**: usage adapter; same laws.
Each slice: fixture-driven tests (no live calls in CI), FR-22 tier test,
provenance + dedup stats per row, honest per-tier detector coverage in
reports, wizard illustration per R-WIZ-ILLUSTRATION, key encryption on the
existing HKDF/Fernet path, journey-suite additions. Money law: every new
pricing row = golden + NOTES derivation, founder-verified BEFORE merge.

**WP-COPILOT-AGG — Copilot admin export ingest (est. 2 days):** parse the
admin seat/usage export (T1-style upload first — no API dependency),
seat-waste findings per the WP-P2-AGG scope note; honest coverage labels.

**WP-T4-SPEC — the OTLP ingest spec, written NOW (est. 1-2 days, spec
only):** docs/12 gated the spec on "first 3 customer conversations"; this
order supersedes that gate if you confirm (§4 Q2). Deliverable is the
mapping document (gen_ai.* + agent/RAG dimensions → CallRecordFrame,
dual-version attribute handling, content-drop at door) + a build estimate —
NOT the endpoint itself; building it stays a separate approval.

**Landing/docs honesty rider (0.5 day):** a "Works with" section that states
the five tiers plainly, including the Cursor/Lovable truth ("their usage on
your provider keys is already counted; native adapters land when they expose
usage APIs") — sales surface catches up with the architecture, no
overclaiming (figure-inventory law applies).

## 3. Sequencing vs the ruled queue

Nothing already ruled moves: launch → WP-CC-LINK → WP-PIPELINE-UI remain
first. Proposal: WP-CLOUD-T2 slices C-A→C-B→C-C run immediately after
WP-PIPELINE-UI (they are the revenue-side "any environment" proof);
WP-COPILOT-AGG rides behind; WP-T4-SPEC is docs-only and can run in any
gap. M-FLY milestones (PLAN-FLYWHEEL) interleave per its own §4 once R-F1
is ruled.

## 4. Numbered questions for founder ruling

1. Promote WP-CLOUD-T2 (Azure OpenAI → Bedrock → Gemini/Vertex, in that
   order)? Each is its own gated milestone with golden pricing rows you
   verify before merge.
2. Write WP-T4-SPEC now (supersedes the "first 3 conversations" gate), with
   the endpoint build still a separate approval?
3. Promote WP-COPILOT-AGG on the export-upload path (no Copilot API
   dependency)?
4. Approve the landing "Works with" honesty rider (five tiers + the
   Cursor/Lovable truth stated plainly)?
5. Helm chart: keep its registered trigger (first VPC/self-hosted
   customer), or pull it forward as part of the "any environment" story?

— END. Awaiting founder approval + rulings on §4. No application code
before approval.
