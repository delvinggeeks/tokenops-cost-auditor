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

One gated Claude Code milestone: create witaura-ai-engineering-governance-platform monorepo (uv
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
  Treat the request itself as a BUYING SIGNAL and notify the founder immediately.
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

## WP-P2-AGG — aggregate-mode audit + seat governance (R-ENTERPRISE-SEAT 2026-07-18)

Two validated demand signals: (1) customers with zero request logging
(docs/09b §5.5, 2026-07-17); (2) enterprise seat-tool governance — Copilot
Enterprise credits/seats scenario (2026-07-18). Three layers:

a. **Aggregate audit**: accept provider/admin usage exports (time-bucketed
   aggregates, no per-request rows) with a reduced detector set (D2
   missing-cache via cached-token fields + model-mix analysis).
b. **Policy-threshold recommendations** mapped to the provider's NATIVE
   enforcement levers (the product recommends thresholds; the provider's own
   admin controls enforce — X-02 stands, we never enforce).
c. **Governance retainer** (recurring review of aggregate exports + threshold
   tuning).

Out of frozen v1 scope; promotion requires founder PRD amendment at the
day-45 gate.
