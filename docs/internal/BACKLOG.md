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

- **WhatsApp daily-digest delivery** — trigger: India Pro cohort >50 subscribed AND
  email-open evidence weak (R-DAILY-LOOP 2026-07-22: the true India-ecosystem
  channel, but a new vendor surface; email digest ships first, this is the escalation).
- **Success-fee enterprise experiment** — trigger: first quarter with verified-savings
  history on an enterprise one-shot customer (R-PRICING-FINAL §1: "$500 minimum or
  10-15% of VERIFIED first-quarter savings", needs a Terms addition).
- **Sign in with Apple** — trigger: a real iOS/App Store surface, or the first customer
  request (R-FED-MAJORS 2026-07-21: Apple private-relay defeats the work-email identity
  everything keys on — needs an identity-merge design, not just a fourth registry row).
- **Queue/workers** (replacing BackgroundTasks + NFR-13 cap) — trigger: the
  MAX_CONCURRENT_AUDITS cap regularly saturated (queue depth alerts in digest).
- **SSO** (O-3; R-ORG relaxed X-03 to permit product-governance roles + enterprise SSO —
  workspaces/RBAC shipped O-0..O-2/O-4, SSO itself stays parked) — trigger: first team
  customer. First identity provider = Microsoft Entra ID (SAML/OIDC), SCIM after
  (R-ENTERPRISE-READY a).
- **SOC2 track** — trigger: enterprise procurement blocker.
- **Helm chart** — trigger: first VPC/self-hosted customer (R-MARKETPLACE a).
- **Kubernetes attribution at T4** — k8s workload attribution rides free on OTel
  resource attributes once T4 STREAM builds (k8s.namespace/deployment/pod alongside
  gen_ai.usage.* spans) — a GROUP BY, not an agent; no sidecar/eBPF until a customer's
  stack can't emit OTel. Trigger: T4 build (first streaming customer).
- **Self-hosted inference metering** (vLLM/TGI/Triton) — self-hosted servers expose
  token counters on Prometheus /metrics; needs a GPU-hour-derived rate card (money-math
  discipline applies, not a provider price sheet). Trigger: first self-hosted-inference
  customer.
- **AWS/Azure/GCP Marketplace listings + IaC templates** (ARM/Bicep, CFN/CDK, Terraform)
  — trigger: second enterprise deal, or first requiring marketplace procurement
  (R-MARKETPLACE a; R-ENTERPRISE-READY c).
- **Control-plane early access** — signup counts (landing CTA, R-GTM-CONTROL) are
  Phase-2 trigger evidence, tracked weekly in the daily digest. Trigger: 25 cumulative
  signups → founder notification line in the digest.
- **CD / auto-deploy-on-tag** (R-DEPLOY-AUTOMATION 2) — trigger: (a) >1 app ships from
  the monorepo (post WP-PLAT-0), OR (b) deploy frequency exceeds 1/week for a month.
  Until then deploys are founder-initiated, ONE command, human-observed.
- **Concierge onboarding** (R-MAGIC-CONNECT 2026-07-22 §4) — GTM register, not a build
  item: "book 10 minutes, we do it on a call with you". Trigger: >5 new paying
  customers in any week (the call stops scaling → onboarding automation becomes a
  build item).
- **Org-level source identity** (R-MULTI-SOURCE 2026-07-23) — the same-key fingerprint
  guard can't catch two DIFFERENT admin keys of the SAME provider org. Hardening: fetch
  the org id during wizard validation, enforce uniqueness per (provider, org). Trigger:
  first support incident of a double-connected org, or provider-OAuth (below) firing.
- **Provider OAuth for usage scopes** (R-MAGIC-CONNECT 2026-07-22 §5) — TRIPWIRE: the
  day OpenAI or Anthropic ships OAuth covering usage reporting, it promotes immediately
  as the connect path and the paste wizard becomes the fallback.
- **D7 EXPORT-CANDIDATE detector** (R-ZTA 2026-07-22 b) — near-identical inference calls
  recurring on a schedule/loop: work that could be inferred once and exported to code.
  Trigger: day-45 gate, or the first customer exhibiting the pattern, whichever first.
- **Act-stage "export this loop" playbooks** (R-ARCH-PATTERNS 2026-07-22 c) — per D7
  finding, a guide from recurring inference to a script/tool. Rides D7's own trigger
  (one event, two deliverables).
- **TASK DECLARATION layer** (R-INTENT-LADDER 2026-07-22 c) — optional route/tag purpose
  declarations (config or dashboard) that detectors consume to sharpen findings;
  counts-safe metadata, FR-22 untouched. Trigger: the T4 STREAM spec conversations
  (declaration is a streaming-era config surface); still needs a PRD amendment.
- **WP-SKILL** — SUPERSEDED 2026-07-23 by R-CC-LINK: folded into WP-CC-LINK below as
  the skill-install step of the one-command install.
- **WP-REPORT-VISUAL** — report web page visual pass (V-D9 deferral, founder-ratified
  2026-07-23 §1): `/report` still wears pre-design-constitution styling while every
  other v1.5 surface moved to wa-design.css. DEFERRED to its own gated milestone (ux +
  vv golden re-verification) because the template is SHARED with the PDF renderer and
  pinned by golden-determinism tests — not a polish-commit rider.
- **Architect lens** (R-PERSONA 2026-07-21 §4) — per-agent/per-pipeline/per-KB
  attribution views, a lens inside the one shell (no persona-forked dashboard).
  Trigger: arrives with T4 span data, never before.
- **"Night Audit" mood** (R-DESIGN-TOKENS-2 §2, 2026-07-25) — dark mood for on-call
  operators; architecture landed 2026-07-25 as a sibling `[data-mood]` value block with
  zero component changes by construction, only the values + AA pass remain. Trigger:
  first on-call/ops customer request.
- **Indic locales** (R-DESIGN-TOKENS-2 §6, 2026-07-25) — the translation-key layer
  ships with the wiring (en only); adding a locale becomes a catalogue, not a refactor.
  Trigger: India-billed accounts reach 25% of paying base, or first hi-IN request.
- **Dark mode** (R-DESIGN 2026-07-20 §2) — LARGELY SUPERSEDED: the app shell's
  sanchaya/aura mood toggle (v1.5.1+) IS dark mode for app surfaces. Remaining scope:
  a public-site toggle only. Trigger: first customer request for a dark public site.
- **RAG waste pattern pack** (R-RAG 2026-07-20) — D2/D3 sub-findings specialized for
  retrieval traffic (cache-breaking chunk placement, over-retrieval, embedding/re-index
  spend); economics only, quality-validation caveat on every finding. Trigger: >=2
  customers show RAG-dominant traffic.
- **Provider/tool expansion queue** (R-AGNOSTIC 2026-07-20) — pull-sequenced, never
  speculative: pricing rows with founder-verified goldens and/or one adapter into an
  existing tier. Seeded order: Gemini, Bedrock, Azure-OpenAI (T2, shipped); Copilot
  admin exports (AGG); per-tool T1 parsers on first customer request each. Cursor/
  Lovable recorded as candidates, blocked today by no public usage/billing API
  (founder walkthrough 2026-07-27) — lands on (first request) AND (an export/API
  existing).
- **Stuck-audit auto-recovery** (D13 deploy evidence 2026-07-19) — audits orphaned in
  `processing` when the serving process dies (observed under uvicorn multi-worker
  ping-kill, fixed by --workers 1; a crash/power-loss can still orphan). Candidate:
  boot-time sweep marking stale `processing` audits failed. Manual path today: admin
  rerun. Trigger: any recurrence in prod, or the queue/workers item above promoting.

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

## WP-CC-LINK — device-link install (R-CC-LINK 2026-07-23)

CORE JOURNEY SHIPPED 2026-07-23 (docs/04-TRACEABILITY.md row: migration 016
link_codes/devices, web/routes_devices consent-refusing link + hashed tokens +
revoke, cli link/ship, services/collector/transcripts, sources.html machines
UI, cron helper). Consolidated WP-SKILL + WP-COLLECTOR into this one
subscriber deliverable — a customer never runs two commands.

RESIDUE (live, trigger: immediately post-v1.5 launch, est. 2-3 days): PyPI
publish of `tokenops-cost-auditor` (full name only, R-NAMING — no short
name), Claude Code skill auto-install (WP-SKILL folds in here as this step),
pipx self-update path so the fleet does not rot.

LAW — ONE HUMAN ACTION IS THE FLOOR, NEVER ZERO (R-CC-LINK 2, permanent).
Remote or silent install is FORBIDDEN as a matter of trust posture: we ask
people to install an auditor inside the agent holding their credentials, so
the consent screen is a marketed FEATURE, not friction — "you'll see exactly
what we collect before anything runs."

SDK/proxy note (R-CONNECT 3): remains Phase-2 control plane — X-01/X-02
intact for the audit product; in-path components live in the customer's VPC
per the deployment contract, post-trust.

## Design-audit P3s (founder deep-audit order 2026-07-26; numbered per docs/design/DESIGN-AUDIT.md)

Batch trigger (founder-approved 2026-07-22): fold into WP-PIPELINE-UI /
WP-REPORT-VISUAL — whichever first touches each item's surface; none
warrants its own round.
- F11 severity chips: mono-caps boxes read as debug badges; consider dot+word
  (Linear label grammar) next time findings surfaces are touched.
- F12 findings sort glyphs render small/cropped; redraw the sprite arrow.
- F13 sample-report stat-card label wrapping → WP-REPORT-VISUAL (already deferred).
- F14 `.nav-group a` declared twice (base + density pass) — values consistent
  today; consolidate on next touch.
- F15 landing mobile: hero capture below the fold (copy+CTA above it) —
  revisit with post-launch funnel data.
- F17 (ux-reviewer note at the FR-32 mockup gate, 2026-07-23): `--serif`
  token is defined in wa-design.css but never referenced — money figures
  render in --sans, not the serif display numerals R-DESIGN #4 calls for.
  Design-system-wide; fold into the next surface-wide visual pass, not a
  per-page fix.

## WP-FRAMEWORK-ADAPT — frontend framework migration path (founder, 2026-07-26)

Recorded per CLAUDE.md rule 1: an X-05 change is a founder ruling, never a
drive-by. Today's stack (SSR + Jinja + htmx, semantic role tokens, one kit,
no build step) is deliberate: §5 server authority, values-only mood swaps,
JS<15KB budgets, single-artifact deploy, one pinned toolchain. If the product
outgrows it, we ADAPT rather than resist — but on triggers, not fashion.

TRIGGERS (any one, reviewed at day-45 or later):
- A surface genuinely needs heavy client state: live editable tables,
  optimistic updates, collaborative sessions, chart brushing/zooming.
- htmx + vanilla passes ~30KB total app JS or interaction latency starts
  costing comprehension (measured, not felt).
- Team scaling makes framework familiarity the hiring bottleneck.

MIGRATION PATH (what makes this cheap later — protect these now):
- The KIT is the unit of migration: each macro's semantic markup + role
  tokens port 1:1 into components; migrate as ISLANDS on the pages that
  triggered the need, never a big-bang rewrite.
- The token map survives any framework: components must keep referencing
  roles (--accent, --money…), never utility hues — moods stay value sheets.
  Tailwind, if adopted, is configured to EMIT the role tokens, not replace
  them; the hex-grep/AA/mood-symmetry tests keep running unchanged.
- §5 stays law: client components render server-decided payloads; every
  money-affecting mutation still round-trips with server re-check + the
  consequence-in-words ask.
- Budgets are re-negotiated at the ruling, not silently blown; the three
  signatures and honest-states law are framework-independent and survive.

Until a trigger fires: new ideas here, never into code.

## R-SAAS-BASICS deliberate absences (founder, 2026-07-26) — triggers, not gaps
- Data export (JSON zip of counts/reports): first customer request OR first
  EU enterprise review.
- Provider API-key payment adapters (programmatic subscription cancel; ends
  the manual provider-side closure step in close-account): first paid-plan
  churn month, or sooner if closures exceed ~1/week.
- SSO / multi-user orgs: X-03 trigger (first genuine team-seat demand).
- Customer API keys: first integration request.
- PWA/native: only after analytics show repeat mobile usage.
- Public changelog page: first post-launch docs batch (generated from
  CHANGELOG.md, no second record).

## WP-REPORT-EXPLORER — FR-32 SHIPPED (R-EXPLORER PRD amendment 2026-07-23)

/explore filters (date range, grouping, source tier, model, finding type,
severity, feedback status) + SAVED VIEWS (migration 014 saved_views) are
BOTH shipped (docs/04-TRACEABILITY.md FR-32 row). RESIDUE (parked, ROADMAP
§5 data-export trigger): "export this view" (C3) — HELD pending
PLAN-FLYWHEEL §6 Q6 ruling on whether it ships early or waits for the
data-export trigger.

## WP-PIPELINE-UI residue — follow-ups noted during/after the shipped runs observatory (FR-31)

The runs ledger + per-stage drill-in + connector pull lineage + alert
evaluation history (FR-31) shipped — see docs/04-TRACEABILITY.md. Open
follow-ups from that build and the depth-engine detour:

- F16 (connect-first gate, 2026-07-27): wa-public.css carries raw px font
  sizes throughout; tokenize a public type scale next time the sheet is
  touched broadly.
- SDK atexit retention (S-1 cold re-gate note, 2026-07-23, non-blocking):
  each `init()` registers `Batcher.close` with atexit but never
  `atexit.unregister`s a prior closed instance, so a process that re-inits
  thousands of times retains that many small callbacks (object retention,
  not a thread/socket leak). One-line fix in `close()` when touched next.
- OAuth authorize deep-link return (S-6 scope note, 2026-07-24): a
  logged-OUT user hitting /oauth/authorize sees a "sign in to authorize"
  interstitial linking to /login, but after login lands on /dashboard —
  they must reopen the app's authorize link. Polish: carry the authorize
  URL through login (a `next=` on /login honored by the verify redirect).
  Bounded out of S-6 to avoid auth-core surgery; the interstitial is honest
  in the meantime.
- [O-COH / R-Q6] Paused-source banner CTA. `metrics.has_live_feed` counts only
  `status=='active'`, so once R-Q6 downgrade-pause starts assigning `status=='paused'`,
  a workspace whose only source is paused (still LISTED on the Sources page,
  `!= 'revoked'`) will trip the data-coherence banner with a "Connect a source" CTA
  that's the wrong instruction — the right one is resume/upgrade. `paused` is not
  assigned anywhere in code today, so this is forward debt, not a live bug. When R-Q6
  ships: branch the banner CTA on a paused-but-listed source.
- MORE FINDINGS / RICHER DETECTION (founder-chosen follow-up, 2026-07-25). Per-request
  logs (upload/SDK) run all 6 savings detectors PER ROUTE; connected provider usage
  APIs give coarse day×model aggregates so only D1/D2/D3 run — stated honestly
  in-product, not a bug. Ongoing direction: (a) more waste detectors (each needs a
  money-math golden per CLAUDE.md rule 4); (b) richer per-route/per-model breakdowns;
  (c) surface the aggregate-vs-per-request depth gap more prominently. Stays
  DETERMINISTIC (X-04 — no LLM narrative).
- CROSS-AUDIT DRIFT — FOLLOW-UPS (after the Breakdown "vs your last audit" slice,
  2026-07-25; the base drift view is shipped). Natural extensions, each a clean
  deterministic slice: (a) DRIFT ALERTING — regressions beyond the material bar
  surface through the existing alerts/daily-digest channel (observe-only, X-02); (b)
  PER-MODEL / PER-ROUTE DRIFT — drill the trend into which model/route drove the
  regression; (c) MULTI-AUDIT TRENDLINE — a sparkline over the last N audits rather
  than a single prior comparison. All stay DETERMINISTIC (X-04), diffs of already-
  priced tokenomics.json figures, FR-22 counts-only.
- "SIX DETECTORS" COPY IS STALE — narrowed 2026-07-28: the customer-facing copy in
  landing.html/_first_run.html/findings.html/tour.js/how-it-works.md has since been
  corrected; `docs-site/engineering/performance.md` is the ONE file still saying "six
  detectors" against the current nine (d1-d6 savings + d8/d9/d10 informational).
  Needs the same honest six-savings-vs-informational distinction, not a mechanical
  find-replace.
- ANOMALY DEPTH-ENGINE — NEXT SLICES (after D10, 2026-07-25; item (a) cross-audit
  drift is now covered by the dedicated CROSS-AUDIT DRIFT follow-ups above, so it's
  dropped here to avoid duplication). Remaining: (b) INTRA-DAY / FINER GRANULARITY —
  hourly buckets so a single-day-dense upload can still surface a spike (D10 needs
  >=7 days today); (c) SEED THE SAMPLE with a multi-day planted spike so the first-run
  preview demonstrates anomaly detection (changes the sample figures, ripples to
  test_guided_first_run, so a scoped follow-up); (d) DAY-OF-WEEK / SEASONAL BASELINE
  (cold-reviewer note on D10) — a legitimately recurring heavy day (weekly batch)
  re-flags every occurrence today (honest — the finding asks the user to verify); a
  day-of-week baseline would stop re-flagging a known pattern. All DETERMINISTIC
  (X-04), FR-22 counts-only.
- INFORMATIONAL FINDINGS — SURFACE THE PER-INCIDENT FIGURE (ux-reviewer note on D10,
  2026-07-25). D10's per-incident number (spike day's excess $, the multiple) lives
  only in fix_text, not a structured slot, because FindingRow persists only
  {route, severity, monthly_impact, confidence, fix_text, evidence} — not the
  detector's detail{} dict. Follow-up: persist FindingRow.detail (JSON column +
  migration) so the drawer can render it prominently — a cross-cutting display change
  across all informational detectors, its own small slice with a ux pass.
- RAZORPAY CALLBACK_URL FALLBACK (B5, Issue #74 noted follow-up). The Standard Checkout
  modal is an iframe; browsers that block third-party iframes (Instagram/FB Messenger/UC
  in-app browsers) can't complete it. Razorpay's `callback_url` redirect-based fallback
  covers those; not built this slice (the modal path covers standard browsers).
- RAZORPAY SUBSCRIPTION UPGRADE/DOWNGRADE (Issue #79 noted follow-up). This slice only
  creates a fresh plan+subscription per checkout; moving an already-subscribed account
  between Pro and Scale mid-cycle is cancel-and-resubscribe, not an in-place swap. A
  proper upgrade/downgrade path (prorated or next-cycle) is a follow-up slice.
- STRIPE SUBSCRIPTION UPGRADE/DOWNGRADE (Issue #81 noted follow-up). Same limitation as
  the Razorpay row above, now also true of the recurring USD Checkout Session: mid-cycle
  Pro↔Team moves are cancel-and-resubscribe, not an in-place swap.
- MCP READ-TOOL PARITY GAP (Issue #85 noted follow-up; PARKED, ROADMAP §5
  R-SCOPE-STOP ← first programmatic-access request). MCP server ships
  `list_audits`/`list_findings` (R-PLATFORM slice 2, Issue #54); no MCP tool wraps
  `get_audit` or the newer `GET /api/v1/audits/{id}/breakdown` yet, and the
  `/breakdown` HTML page's "vs your last audit" trend is not part of the read API
  either — both ride the same R-SCOPE-STOP trigger, not a separate signal.
