# WitAura AI Agentic Engineering Governance Platform — Architecture v1.0

Founder: Lokesh Prasanna Kumar S · 2026-07-18
[Name corrected per founder 2026-07-18 (final): "WitAura AI Agentic Engineering Governance Platform" — applied throughout, incl. repo slug.]
Status: APPROVED ARCHITECTURE. Governs how every feature from the
strategy table becomes a first-class module of ONE platform.
Companion to WITAURA-MASTER-STRATEGY.md (strategy, founder-side) and the
product spec kit (build scope).

Repo note: this document's permanent home is `docs/platform/` in the
witaura-ai-agentic-engineering-governance-platform monorepo (created at WP-PLAT-0, §6). It is recorded here in
the v1 repo verbatim as the founder-authored document of record; the v1 repo
is NOT restructured pre-launch (§6 timing rule).

---

## 1. What "platform" means here, precisely

One buyer (engineering leadership running AI/agent workloads), one
account, one deployment contract, one shared engine core — many
feature modules that ship independently and integrate through defined
contracts. Features are packages, not forks. Nothing is a register
entry anymore; everything below has a home address in the tree.

## 2. Repo topology decision (ruled)

DECISION: **Platform monorepo with uv workspace packages** — not
multiple feature repos with a main integration repo.

Why (honest engineering tradeoff for a solo founder + agent builds):
- Multi-repo demands version-matrix management, cross-repo CI,
  package publishing, and integration-repo sync — a full-time
  platform engineer's job. Monorepo gives atomic cross-cutting
  changes, ONE CI, ONE traceability matrix, ONE gate-agent harness
  covering everything, and shared golden fixtures.
- Claude Code + our harness work dramatically better with the whole
  platform in one context-addressable tree (diff-only gates, single
  STATUS.md, single CLAUDE.md).
- Independent shipping is preserved: each app in the workspace builds
  its own container image and versions independently via tags
  (auditor-v1.2.0, controlplane-v0.3.0). Monorepo ≠ monolith.
- Escape hatch: if a module ever needs a separate repo (e.g., an
  open-source release of the harness), workspace packages extract
  cleanly — the boundary already exists.

## 3. The platform tree (target structure)

```
witaura-ai-agentic-engineering-governance-platform/
├── CLAUDE.md                  # one harness, one token economy
├── STATUS.md                  # one shared memory
├── docs/                      # platform-level spec kits, per-module
│   ├── platform/              # this doc, deployment contract, ADRs
│   ├── auditor/               # existing 00-10 spec kit (moves here)
│   ├── controlplane/          # spec kit written at promotion
│   ├── buildhealth/
│   └── comprehend/
├── packages/                  # shared libraries (import-only, no apps)
│   ├── wa-core/               # CallRecord model, config, obs,
│   │                          # persistence base, error envelope
│   ├── wa-pricing/            # four-rate versioned table, coster,
│   │                          # golden discipline (THE money engine)
│   ├── wa-detectors/          # D1-D6 + future detectors; registry;
│   │                          # findings/evidence types (FR-22 lives
│   │                          # here); import-guard applies here
│   ├── wa-report/             # ReportModel, JSON/PDF/web renderers,
│   │                          # signer, methodology blocks
│   └── wa-harness/            # gate agents, TE rules, TEACH
│                              # protocol, spec-kit templates —
│                              # productizable for Idea #2 services
├── apps/                      # deployable products (each = image)
│   ├── auditor/               # TokenOps Cost Auditor (current v1,
│   │                          # relocated intact)
│   ├── controlplane/          # P2-A: policy engine, budgets, stops
│   ├── buildhealth/           # discipline scorecard (report mode
│   │                          # over wa-detectors aggregates)
│   └── comprehend/            # P3: evidence-anchored retrofit
├── exporters/                 # onboarding products: claude-code,
│   │                          # openai/anthropic jsonl, aggregate-
│   │                          # mode (WP-P2-AGG), copilot-admin
├── deploy/                    # compose bundles per app, Helm charts,
│   │                          # marketplace IaC (ARM/CFN/Terraform)
│   │                          # — all obeying R-DEPLOYMENT-CONTRACT
└── ops/                       # backup, digest, pricing-watch
                               # (WP-P1.5), self-audit ledger
```

## 4. Integration contracts (how modules stay independent)

C-1 DATA: CallRecordFrame (wa-core) is the lingua franca. Every
    exporter produces it; every detector consumes it; aggregate-mode
    defines a reduced AggregateFrame with a declared detector subset.
C-2 MONEY: only wa-pricing computes cost; only wa-detectors emits
    Finding objects; golden-file + founder-verification ritual is a
    platform law, enforced per-package.
C-3 EVIDENCE: every module's outputs carry citations (evidence rows,
    file:line anchors, rate provenance). Uncited claims are a
    platform-wide FAIL condition — audits, docs, comprehend alike.
C-4 PRIVACY: FR-22 (counts/metadata only; no prompt text persisted)
    is a platform invariant enforced in wa-detectors types + tests;
    every app inherits it.
C-5 DEPLOYMENT: every app ships as a single placeable artifact under
    R-DEPLOYMENT-CONTRACT (zero egress, BYO infra, air-gap bundles).
C-6 IDENTITY/DB: apps share the account model (users → later orgs/
    Entra SSO at the X-03 trigger) and additive-only migrations.
C-7 HARNESS: every module is built under wa-harness gates with its
    own spec kit; no module merges without traceability rows.

## 5. Feature → module map (every idea has an address)

| Strategy item | Platform home | Ships when |
|---|---|---|
| Cost Auditor (v1) | apps/auditor | SHIPPED (D13/D14 pending) |
| Claude Code exporter | exporters/claude-code | shipped |
| Pricing-watch (WP-P1.5) | ops/pricing-watch | week 3-4 |
| Self-audit ledger (WP-SELF) | ops/self-audit | with D14 |
| Aggregate/seat audit (WP-P2-AGG, Copilot governance) | exporters/aggregate + apps/auditor mode | day-45 gate |
| Control plane (P2-A: budgets, hard stops, loop kill-switch, routing) | apps/controlplane | customer pull post day-45 |
| Build Health (WP-P2-BUILDHEALTH) | apps/buildhealth | day-45 gate |
| Comprehension retrofit (WP-P3-COMPREHEND) | apps/comprehend | day-45 + 2 paid #2 engagements |
| Idea #2 services ("ownable AI software") | wa-harness productization + docs | offer sheet after D14 |
| Model-release regression (idea #3) | apps/auditor feature | with retainer customers |
| Voice-agent QA (idea #4) | future apps/voiceqa (same contracts) | table |

## 6. Migration plan (existing repo → platform, WP-PLAT-0)

Timing: **week 3, immediately after D14 launch** — never before
first customers. The v1 repo is NOT restructured pre-launch.

Steps (one Claude Code milestone, gated):
1. Create witaura-ai-agentic-engineering-governance-platform repo with the tree above; move the
   existing repo to apps/auditor + split packages/ out of
   src/tokenops_cost_auditor (pricing→wa-pricing, rules→wa-detectors,
   report→wa-report, config/obs/persistence base→wa-core) as uv
   workspace members. Import paths change; CLI name, image name, DB
   name, product name DO NOT (R-NAMING intact).
2. Traceability matrix gains a "package" column; all 197+ tests move
   with their modules; suite must be green with byte-identical
   report JSON on the golden fixtures before merge (the determinism
   test is the migration's acceptance gate).
3. Gate agents' charters update paths; harness itself moves to
   wa-harness.
4. Tag platform-v1.0.0. From then on, every new feature is a
   workspace citizen from birth — no more single-product repo.

## 7. What this architecture makes true

- "Multiple features, single platform": yes — as packages/apps with
  contracts, atomically testable, independently shippable.
- "Scalable": each app scales per its own profile under the shared
  deployment contract; data-not-logins user model platform-wide.
- "Adopting into existing enterprise environments": deploy/ artifacts
  per app per cloud; CLI-inside-perimeter remains the universal
  data-residency answer.
- The platform NAME on the masthead ("WitAura AI Agentic Engineering Governance Platform") activates at the day-45 gate per R-BRAND — the
  architecture doesn't wait for the name.
