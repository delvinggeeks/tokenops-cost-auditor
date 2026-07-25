# ROADMAP — Outstanding Work, single source of truth

**Purpose.** ONE place for every outstanding requirement + the process, so nothing is
missed or diverted. Consolidated 2026-07-25 from a full sweep of all plan docs
(PLAN.md, PLAN-V15/ORG/SDK/TAAS/COPILOT/FLYWHEEL/LOOP-ENGINEERING, PLATFORM,
00-PRD, 01-REQUIREMENTS, 07-ROADMAP, 11-PLATFORM-ARCHITECTURE, 12-FLYWHEEL,
13-T4-OTLP, KANBAN, BACKLOG, launch/*, UAT2-KIT, STATUS).

**How to use.** §3 is the working queue — build top-down. §4 is the founder's lane.
§5 is parked-by-design (do NOT pull one forward without its trigger firing). §1 is
the do-not-build wall. §2 is the process every slice obeys.

**Authority.** This board is the MAP; the per-track PLAN-*.md docs are the territory
(detailed spec). It SUPERSEDES the stale KANBAN.md 2026-07-24 snapshot as the working
queue. `docs/07-ROADMAP.md` remains the strategic Phase-1/2 narrative. STATUS.md is
the running build log.

---

## 0. Baseline — SHIPPED and LIVE (prod v1.9.0)

Everything below is done, gated, in production — do NOT re-open:
- **Audit v1.0** (D1–D14): ingest (OpenAI/Anthropic JSONL + CSV + Claude Code exporter),
  four-rate pricing + golden discipline, six deterministic detectors, report JSON/PDF/web,
  auth/payments/admin/purge/ops. **All FR-01…FR-32 and NFR-01…NFR-15 traced-done.**
- **Monitor v1.5** (WP-1…7): T2 connect (5 providers), owner dashboard, alerts
  (observe-only), L0 feedback + verified savings, Savings Statement, settings,
  subscriptions + dunning, federated sign-in, live pricing sync, daily digest.
- **Org**: O-0 workspace spine, O-1 members/invites/revoke (PRs #13–16).
- **SDK/platform**: S-0/S-1 ingest DSN, S-6 read API + OAuth + developer settings.
- **Flywheel**: L0 feedback, M-FLY-0 frame+cohort, M-FLY-1 L1 peer benchmarks,
  deterministic forecast (alert-only), consent toggle.
- **Collector**: T3 device link (WP-CC-LINK core). **Runs observatory** (FR-31).

**In-flight THIS session (2026-07-25) — depth-engine, built AHEAD of the §3 frontier
(a divergence; see note):**
- Merged to main: guided-first-run (#17), richer-findings D8/D9 (#18), tokenomics
  breakdown (#19), relatable landing (#20).
- Held for founder merge: D10 within-audit anomaly (#21), cross-audit drift (#22) —
  both green. Their follow-ups (tokenomics slices 2–5, more detectors, drift alerting)
  stay parked in §5 unless prioritized here.

---

## 1. Scope guardrails — do NOT build (docs/01 §G)

| ID | Forbidden | Status |
|----|-----------|--------|
| X-01 | Live proxy / gateway in the customer's traffic path | FORBIDDEN (in-path only ever inside customer VPC, Phase-2 post-trust) |
| X-02 | Policy / budget ENFORCEMENT of customer LLM traffic | FORBIDDEN — observe-and-alert only |
| X-03 | Multi-org RBAC / SSO | RELAXED-but-BOUNDED by R-ORG: product-governance roles + enterprise SSO PERMITTED; audit engine stays TENANT-BLIND; roles never gate LLM traffic |
| X-04 | LLM-generated narrative in reports | FORBIDDEN — deterministic label factory only |
| X-05 | SPA frontend | RELAXED to SSR + htmx ONLY (no framework, no build step) |

---

## 2. Process — the flow + Definition of Done (every slice obeys this)

**Flow:** Issue → vertical slice → branch off `main` → implement → CI + gate round →
PR → founder merge → deploy (founder-gated) → verify.

**DoD (a card is DONE only when ALL hold — KANBAN law):** tests per docs/05 pattern ·
docs/04-TRACEABILITY updated same commit · golden NOTES for any money math · FR-22
tier tests · honesty-law rendering (honest empty/error states) · gate verdicts TE-8 ·
ux mockup-before-wiring on new surfaces · STATUS.md paragraph · conventional commits
(NO AI trailers) · ≤3-day slice · **R-VERTICAL: the slice contains its UI + click path
+ journey test + ux gate — a user finishes the job in ONE milestone, never a layer at a
time.** Reachability: shipped ≠ exists until a customer can click to it.

**Machine laws:** authorship (LE-1) · X-scope · FR-22 (no prompt/completion text stored,
ever) · money law (`pricing_verify.py` — a wrong rate fails the build) · traceability ·
engine boundary (T-NFR-01: `services/rules` + `services/pricing` tenant-blind, zero
network/LLM imports; tenancy only at the web/persistence boundary).

**Gates (TE-8 verdict):** cold-reviewer · spec-guard · vv-engineer · system-tester ·
ux-reviewer · architect · ops-engineer. **CI:** authorship · ruff · mypy · pytest+cov ·
pricing-verify · docs-drift. **Deploy:** backup → provision → smoke → auto-rollback.

**Tracking:** STATUS.md (build log) + this file (queue). NO task-tool kanban.

---

## 3. BUILDABLE NOW — the frontier, in priority order

The only items with NO unmet trigger and NO founder-lane dependency. Build top-down.

| # | Item | Track | What / DoD | Est | Depends |
|---|------|-------|-----------|-----|---------|
| 1 | **O-2 Roles / RBAC** | ORG | `owner\|admin\|member\|viewer` matrix over PRODUCT actions (mint/revoke keys, manage billing, manage sources, view-vs-manage reports), enforced at the route boundary; engine role-blind. DoD: each role's rendered surface pinned — a viewer can't even SEE a control they can't use. Unblocks billing-visibility + member-mutates fail-closed since O-1. | 2–3d | O-1 (done) |
| 2 | **View-report reachability** | REACH | No in-app click path to `/r/{token}` today (email-only). Add a "View report" affordance + journey test + reachability inventory. A real R-REACHABILITY gap. | 0.5d | — |
| 3 | **Report plain-English (PDF/web)** | REPORT | Carry the plain/summary detector copy into ReportModel so the downloadable report matches the in-app findings (fast-follow of #17). Needs the display copy moved to a services-accessible source. | 1d | #17 (merged) |
| 4 | **Landing "Works with" rider** | LANDING | Five provider tiers stated plainly incl. the Cursor/Lovable truth. Small honesty add. | 0.5d | next landing touch |
| 5 | **R-LANDING-2 rebuild** | LANDING | 3 new sections (animated pipeline, product-tour tabs, comparison strip) on the v4 skeleton. GO issued 2026-07-25; distinct from #20's re-tone. | 2–3d | design |
| 6 | **M-FLY-2 (L2 calibration, SHADOW)** | FLYWHEEL | Deterministic grid over existing config knobs proposes per customer×detector thresholds; report-JSON + admin calibration block; findings BYTE-IDENTICAL (shadow only, B3 apply stays off). | 2–3d | M-FLY-1 (done); n≥25 data |
| 7 | **O-4 Workspace settings home** | ORG | Gather General · Members · Auth · Audit Log into one settings surface. Organizing surface, no new capability. | 1–2d | O-2 |
| 8 | **Design P3 batch (F11–F17)** | DESIGN | Severity dot+word grammar, sort-glyph sprite, nav-group dup, retired --serif numerals, public type-scale tokens — fold into the next surface touch. | 1d | next surface touch |
| 9 | **Coverage debt** | QA | smtp.py 83.8% · purge.py 78.9% · schedule.py 84.8% → target. | 0.5d | — |

**Recommended sequence:** #1 O-2 RBAC first (the plan's actual next milestone, unblocks
the most), then the quick honesty/reachability wins (#2–#4), then #5/#6 as larger slices.

**Not "now" despite looking buildable:** WP-PLAT-0 monorepo migration (explicitly
"never before first customers"); O-3 SSO (X-03 trigger: first team customer — see §5);
LE-3…LE-6 loop automation (depend on LE-2, which is founder-lane §4); UAT-2 (founder-
executed §4).

---

## 4. FOUNDER-OWNED — launch blockers, secrets, decisions (I cannot do these)

- **UptimeRobot** public status page + CNAME `status.tokenops-cost-auditor.com` (footer link must resolve before launch).
- **Stripe** dashboard credentials; payment links at LAUNCH prices + webhook secrets; **OAuth** credentials per provider.
- **Production walkthrough** ACCEPT/HOLD after a deploy.
- **Provider-side subscription closures** when the daily digest flags one (manual until API-key adapters).
- **Deploy secrets** `DEPLOY_HOST`/`DEPLOY_DOMAIN`/`DEPLOY_SSH_KEY` + one validated run → un-holds **LE-2** (continuous deploy), which unblocks LE-3…LE-6.
- **Branch protection** on `main` (green-PR-only).
- **Domain cutover** DNS A-records (R-DOMAIN-MIGRATE, blocked on DNS).
- **Day-45 revenue gate** (5 delivered / 2 paid else pivot) — also gates WitAura name activation, Build-Health/Comprehend rings.
- **Merges:** depth-engine PRs #21, #22 (held, green).
- **Rulings pending:** India-pricing $ vs ₹ asymmetry; loop-autonomy dial (hands-off vs comprehension checkpoint on load-bearing changes); R-F1 amended cross-customer-benchmark promise sentences (sign-off before any copy/test change).
- **UAT-2** send + record evidence; **TEACH** curriculum sessions (founder-initiated).
- **Prod hygiene:** the `--proxy-headers` rate-limit fix lands on the NEXT deploy (currently a global bucket in prod).

---

## 5. TRIGGER-GATED — parked BY DESIGN (do NOT pull forward without the trigger)

Each fires on a named customer/demand event. This is intentional scope discipline, not a
backlog of forgotten work.

**SDK / platform**
- S-2 **T4 OTLP endpoint** (`/api/v1/otlp/v1/traces`, gen_ai.*→CallRecordFrame, content dropped at door) — HELD, spec (docs/13) approved-to-exist, endpoint is a SEPARATE founder approval on first streaming-customer conversation (~3–5d). Also: K8s attribution, per-agent/RAG attribution, FOCUS export — all ride the T4 build.
- S-3 **MCP server** over /api/v1 (read tools) — API-key buying signal. Write tools after.
- S-4 JS/TS SDK; S-5 GitHub Action + Slack delivery; outbound webhooks — later/pull.
- **Customer API keys** (per-key scopes/metering) — first integration request (fires S-3 too).

**Enterprise / deployment**
- O-3 **Enterprise SSO** (SAML/OIDC per workspace, Entra first, SCIM after) — first team customer (X-03).
- SOC2 track — procurement blocker. Helm chart — first VPC customer. Marketplace IaC (AWS/Azure/GCP) — second enterprise deal. Self-hosted inference metering (vLLM/TGI Prometheus + GPU rate card) — first self-hosted customer. T5 in-VPC gateway/control-plane — in-VPC procurement demand. Security-questionnaire portal — post-launch.

**Detectors / intelligence**
- D7 export-candidate detector + Act-stage "export this loop" playbooks — day-45 or first pattern-exhibiting customer. Architect lens (per-agent/pipeline/KB attribution) — T4 span data. Task-declaration layer — T4 spec. RAG waste pack (D2/D3 sub-findings) — ≥2 RAG-dominant customers. Provider expansion (Gemini/Bedrock, Copilot admin exports, per-tool T1 parsers) — pull-sequenced per first request.

**Flywheel rungs**
- B3 L2-active per-detector apply-flag — B2 + ≥1mo shadow evidence. B4 L3 learned forecast/anomaly — n≥50 + 6mo. B5 L4 policy learning — control-plane era. Control-plane EA signup counter — 25 cumulative signups.

**SaaS-basics / infra**
- Data export (JSON zip) — first request / EU review. Queue/workers — MAX_CONCURRENT_AUDITS saturation. Programmatic provider-cancel adapters — churn/closure rate. PWA/native — repeat mobile usage. Public changelog page — first post-launch docs batch. Stuck-audit auto-recovery — any prod recurrence. Org-fingerprint identity hardening — first double-connect incident. Provider OAuth usage-scope — when OpenAI/Anthropic ship it. Framework migration path — heavy client state / >~30KB app JS. CD auto-deploy-on-tag — >1 app or >1 deploy/week/month.

**i18n / design / channels**
- Indic locales — 25% India-billed or first hi-IN request. Public-site dark mode — first request. Night-audit mood — first on-call customer. WhatsApp digest — India cohort >50 + weak email opens.

**Platform rings / Phase-2**
- Control plane (apps/controlplane, P2-A), Build Health ring (apps/buildhealth), Comprehend ring (apps/comprehend), model-release regression, voice-agent QA, retainer productization — day-45 gate and/or customer pull.
- FR-32 view-export hook (C3) — data-export trigger ruling (saved views already shipped).

---

## 6. Notes & reconciliations

- **KANBAN.md is stale** (2026-07-24): its NEXT items 1 (WP-CLOUD-T2/Vertex), 1a (S-6),
  1a2 (O-0), 2 (WP-COPILOT-AGG) have all shipped since. Treat this file as current.
- **Supersessions:** WP-P1.5 pricing human-gate → superseded by R-LIVE-PRICING (auto,
  shipped); WP-COLLECTOR → merged into WP-CC-LINK; dark-mode app aura → shipped (public
  site still parked). L2 calibration = FLY-B2 = docs/12 L2 (one deliverable).
- **The depth-engine detour:** tokenomics/D10/drift were built from an improvised "more
  findings" thread ahead of this frontier. They're merged/held; their follow-ups live in
  §5. Lesson recorded: work §3 top-down; new ideas go to §5, not into code.
- **WORKFLOW-READINESS.md** is fully remediated (all 50 findings closed) except the one
  India-pricing ruling (§4). **UAT-2** is not yet executed.
