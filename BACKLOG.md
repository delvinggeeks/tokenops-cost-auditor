# BACKLOG.md — scope parking lot

Per PRD §10 change control: scope additions during the 14-day build are rejected by
default and parked here. Promotion requires a founder-written amendment in
docs/00-PRD.md.

PLATFORM NOTE (R-PLATFORM-ARCH, 2026-07-18): every item below now has a home
address in the approved platform tree — see docs/11-PLATFORM-ARCHITECTURE.md
§5 (feature→module map) and §6 (WP-PLAT-0 migration: week 3, post-D14, never
before first customers). Triggers and promotion gates below remain in force;
the architecture assigns WHERE things live, not WHEN they ship.

## WP-PLAT-0 — platform migration (R-PLATFORM-ARCH §6; week 3, post-D14)

One gated Claude Code milestone: create witaura-ai-agentic-engineering-governance-platform monorepo (uv
workspace), relocate this repo to apps/auditor, split
pricing→wa-pricing / rules→wa-detectors / report→wa-report /
config+obs+persistence-base→wa-core; traceability gains a package column;
ALL tests move with modules. ACCEPTANCE GATE: suite green + byte-identical
report JSON on golden fixtures. CLI/image/DB/product names unchanged
(R-NAMING). Gate charters re-pathed; harness moves to wa-harness. Tag
platform-v1.0.0.

## Deliberately OUT — trigger register (R-API 2026-07-17; R-ENTERPRISE-READY + R-MARKETPLACE 2026-07-18)

Recorded triggers, not build items. When a trigger fires, notify the founder;
promotion still requires a PRD amendment.

- **API keys / programmatic access** — trigger: first customer request.
  Treat the request itself as a BUYING SIGNAL and notify the founder
  immediately. [R-APIKEYS 2026-07-20, build detail when fired: keys issued
  in Settings, hashed at rest, per-key scopes (submit/read), per-key rate
  limits riding the existing NFR-12 limiter, usage counted per key (the
  metering seed for future usage-based pricing), revocation instant,
  every key event audit-logged. Until then: sessions + CLI cover all
  real users.]
  [R-SKILL 2 (2026-07-23): WP-MCP fires on this SAME event — a request for
  programmatic access is a request for the MCP surface. One trigger, two
  deliverables; do not treat them as separate signals.]
- **Queue/workers (replacing BackgroundTasks + NFR-13 cap)** — trigger: the
  MAX_CONCURRENT_AUDITS cap regularly saturated (queue depth alerts in digest).
- **Orgs/SSO** (X-03 stands) — trigger: first team customer.
  [R-ENTERPRISE-READY a] First identity provider = Microsoft Entra ID
  (SAML/OIDC), SCIM after. Trigger unchanged.
- **SOC2 track** — trigger: enterprise procurement blocker.
- **Helm chart** — trigger: first VPC/self-hosted customer. [R-MARKETPLACE a]
- **AWS/Azure/GCP Marketplace listings + IaC templates (ARM/Bicep, CFN/CDK,
  Terraform)** — trigger: second enterprise deal, or first requiring
  marketplace procurement. Azure Marketplace private offers noted as future
  procurement channel. [R-MARKETPLACE a; R-ENTERPRISE-READY c]
- **Control-plane early access** — signup counts (landing CTA, R-GTM-CONTROL)
  are Phase-2 trigger evidence; weekly count in the daily digest.
- **CD / auto-deploy-on-tag** (R-DEPLOY-AUTOMATION 2) — trigger: (a) >1 app
  ships from the monorepo (post WP-PLAT-0), OR (b) deploy frequency exceeds
  1/week for a month. Until then deploys are founder-initiated, ONE command
  (scripts/provision.sh / deploy/tf, WP-DEPLOY-1), human-observed.
- **Concierge onboarding** (R-MAGIC-CONNECT 2026-07-22 §4) — GTM register,
  NOT a build item: for early customers, "book 10 minutes, we do it on a
  call with you". The solo-founder advantage incumbents cannot match.
  Revisit as a product feature only if it stops scaling.
- **Provider OAuth for usage scopes** (R-MAGIC-CONNECT 2026-07-22 §5) —
  TRIPWIRE: the day OpenAI or Anthropic ships OAuth covering usage
  reporting, it promotes immediately as the connect path and the paste
  wizard becomes the fallback. Until then the wizard is the state of the
  art. Notify the founder when either provider announces it.
- **D7 EXPORT-CANDIDATE detector** (R-ZTA 2026-07-22 b) — near-identical
  inference calls recurring on a schedule or loop: work that could be
  inferred once and exported to code. Output: the recurring shape, its full
  monthly cost, and the zero-token recommendation; recurrence + similarity
  thresholds; confidence=estimated; the quality caveat verbatim. Promotion:
  day-45 gate, or the first customer exhibiting the pattern — whichever
  comes first.
- **Act-stage "export this loop" playbooks** (R-ARCH-PATTERNS 2026-07-22 c)
  — per D7 finding, a guide from recurring inference to a script or tool,
  quality caveat attached. The services bridge.
- **TASK DECLARATION layer** (R-INTENT-LADDER 2026-07-22 c) — optional
  route/tag purpose declarations via config or dashboard; detectors consume
  them to sharpen findings (task-tier mismatch, declared-repetitive → D7
  priority, budget-per-purpose). Declarations are counts-safe metadata —
  FR-22 untouched.
- **WP-SKILL — "tokenops-audit" Claude Code skill** (R-SKILL 2026-07-23 §1)
  — SKILL.md plus scripts wrapping the T1 exporter and the CLI: runs
  entirely on the user's own machine over their own transcripts (UAT-D5
  dedup law, counts-only by construction, nothing transmitted), opens the
  report, and closes with ONE pointer to the monitored product. Distribution:
  skill lists + a docs page. TRIGGER: immediately post-v1.5 launch, est. 1
  day. Its README states the ZTA credential plainly — the skill performs
  zero inference beyond its own invocation.
- **WP-MCP — MCP server over /api/v1** (R-SKILL 2026-07-23 §2) — submit an
  export, poll audit status, fetch findings, so agents and frameworks can
  call TokenOps as a tool. TRIGGER: the existing API-key buying signal
  (same event, modern surface) — see the API-keys entry above.
- **WP-REPORT-VISUAL — report web page visual pass** (V-D9 deferral,
  founder-ratified 2026-07-23 §1) — the /report web surface still wears the
  pre-design-constitution styling while every v1.5 app surface moved to
  wa-design.css. DEFERRED TO ITS OWN POST-LAUNCH GATED MILESTONE, not a
  polish-commit rider, because the template is SHARED with the PDF renderer
  and pinned by golden-determinism tests: a change that looks like CSS can
  silently move a byte in a deliverable customers pay $500 for. It gets a
  full gate (ux + vv golden re-verification), or it does not get touched.
- **Architect lens** (R-PERSONA 2026-07-21 §4) — per-agent /
  per-pipeline / per-knowledge-base attribution views, the T4-era
  architect dashboard. Registered, NOT built: arrives with T4 span data,
  never before (R-AGENTIC-DIMENSIONS + R-RAG already reserve the
  dimensions in the T4 mapping spec). No persona-forked dashboard — it
  is a lens inside the one shell (R-PERSONA §5).
- **Dark mode** (R-DESIGN 2026-07-20 §2) — deferred by the design
  constitution; wa-design.css tokens are structured to admit it later.
- **RAG waste pattern pack** (R-RAG 2026-07-20) — D2/D3 sub-findings
  specialized for retrieval traffic: cache-breaking chunk placement,
  over-retrieval signature, embedding/re-index spend line. Trigger:
  >=2 customers show RAG-dominant traffic. Boundary: economics only;
  every RAG finding carries the quality-validation caveat.
- **Provider/tool expansion queue** (R-AGNOSTIC 2026-07-20) —
  pull-sequenced, never speculative; each addition = pricing rows with
  founder-verified goldens and/or ONE adapter into an existing tier.
  Seeded order: Gemini, Bedrock, Azure-OpenAI (T2); Copilot admin
  exports (AGG); per-tool T1 parsers on first customer request each.
  No per-tool forks — frame contract keeps everything provider-neutral.
- **Stuck-audit auto-recovery** (D13 deploy evidence 2026-07-19) — audits
  orphaned in `processing` when the serving process dies (observed twice
  under the uvicorn multi-worker ping-kill, fixed by --workers 1; a crash
  or power loss can still orphan). Candidate: boot-time sweep marking stale
  `processing` audits failed (or requeueing). Manual path today: admin
  rerun (proven in the D13 recovery). Trigger: any recurrence in prod, or
  the queue/workers item above being promoted.

Explicitly NOT building now (R-ENTERPRISE-READY d): SSO, marketplace
listings, SOC2, security-questionnaire portal.

Enterprise sales notes (R-ENTERPRISE-READY c): CLI-inside-perimeter ("nothing
leaves but the PDF") is the standing lead answer to data-residency and
security review at ALL tiers; security-questionnaire answers to be drafted
from the docs-site Engineering section post-launch.

## R-DEPLOYMENT-CONTRACT (founder 2026-07-18) — governs ALL Phase-2/enterprise design

1. Single deployable artifact placeable in any customer zone by their platform
   team.
2. Zero required egress — offline license files, telemetry opt-in only, no
   phone-home.
3. No assumptions about customer DNS/proxy/internet/reachability beyond
   documented component links.
4. Bring-your-own Postgres/TLS/identity/storage.
5. Versioned offline install bundles for air-gapped delivery.
6. Auditability (append-only logs, deterministic outputs, published
   methodology) maintained as enterprise requirements.

Cloud deployment ladder (R-MARKETPLACE a): compose bundle (exists, v1) → Helm
chart → marketplace listings with IaC templates; every artifact obeys this
contract.

User-model principle for all enterprise design (R-MARKETPLACE b): employees
are DATA SOURCES, never platform users; reader seats ~5-50 per enterprise
regardless of headcount; scaling requirements are data volume and (Phase 2)
policy-decision throughput, not concurrent logins; Entra SSO covers readers
when the X-03 trigger fires.

## WP-P1.5 — pricing-watch pipeline (R-PRICING-AGENT; FIRST post-launch package, week 3-4)

FR-29b, ops-side only: ofelia crawl 2x/week (source_urls + LiteLLM model-prices
JSON cross-check tripwire); hashed raw snapshots; candidates ->
pricing_candidates (pending_review); admin side-by-side diff + one-click approve;
approval writes prices.yaml (effective_from + source), drafts golden-row
suggestion, bumps last_verified. HARD RULES (founder): no auto-approval path in
code; crawler zero write access to prices.yaml; LLM extraction only into
candidate queue; disagreements flagged never auto-resolved; approvals
audit-logged with founder as actor.

## WP-P2-AGG — PROMOTED (R-CONNECT 2026-07-19; PRD amendment recorded): Connect flows, immediate post-polish build (est. 1-2 wks)

[R-CONNECT supersedes the day-45 tripwire below. Build starts immediately
after the R-CONNECT §4 sequence completes (polish → onboard → walkthrough →
launch thread, Connect flows honestly ABSENT from launch claims).]

Promoted scope: **"Connect OpenAI" / "Connect Anthropic" flows** — customer
pastes an org/admin API key; we pull usage server-side via the official
Usage/Admin APIs; reduced detector set as documented since D1 (D2
missing-cache via cached-token fields + model-mix analysis); key handling:
encrypted at rest, revocable, never logged; UI parity with the upload flow.

Original demand signals (kept for the record): (1) customers with zero
request logging (docs/09b §5.5, 2026-07-17); (2) enterprise seat-tool
governance — Copilot Enterprise credits/seats scenario (2026-07-18).
Layers b (policy-threshold recommendations mapped to the provider's NATIVE
enforcement levers — X-02 stands, we never enforce) and c (governance
retainer) remain Phase-2, unpromoted.

## WP-COLLECTOR — registered next after WP-P2-AGG (R-CONNECT 2026-07-19)

pipx-installable watcher for Claude Code transcript dirs: dedup per UAT-D5
law (by request_id, max-complete usage wins, summary printed), counts-only
by construction (FR-22 — no text ever read into the payload), scheduled
ship to the API using FR-26 idempotent uploads. One command, zero code
changes on the customer side. This is the enterprise fleet onboarding.

SDK/proxy note (R-CONNECT 3): remains Phase-2 control plane — X-01/X-02
intact for the audit product; recorded rationale: in-path components live
in the customer's VPC per the deployment contract, post-trust.
