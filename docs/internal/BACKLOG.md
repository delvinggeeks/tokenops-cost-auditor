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

- **WhatsApp daily-digest delivery** — trigger: India Pro cohort >50
  subscribed AND email-open evidence weak. [R-DAILY-LOOP 2026-07-22: the
  true India-ecosystem channel, but a new vendor surface (WhatsApp
  Business API) — email digest ships first; this is the escalation.]
- **Success-fee enterprise experiment** — trigger: first quarter with
  verified-savings history on an enterprise one-shot customer.
  [R-PRICING-FINAL §1 registered the Vantage-Autopilot grammar ("$500
  minimum or 10-15% of VERIFIED first-quarter savings") as a post-launch
  experiment on the enterprise line only; needs Terms addition.]
- **Sign in with Apple** — trigger: a real iOS/App Store surface, or the
  first customer request. [R-FED-MAJORS 2026-07-21: consumer/iOS-mandated;
  Apple's private-relay addresses defeat the work-email identity everything
  keys on, so it needs an identity-merge design, not just a fourth registry
  row. Google/Microsoft/GitHub cover this buyer.]
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
- **Kubernetes attribution at T4** — design note (founder question
  2026-07-22, "how does this sit inside cloud infra"): when T4 STREAM
  builds, k8s workload attribution comes FREE from OTel resource
  attributes (k8s.namespace/deployment/pod ride the same spans as
  gen_ai.usage.* token counts) — per-team/per-service tokenomics is a
  GROUP BY, not an agent. No sidecar/eBPF until a customer's stack
  can't emit OTel. Trigger: T4 build (first streaming customer).
- **Self-hosted inference metering (vLLM/TGI/Triton)** — design note:
  self-hosted LLM servers expose prompt/generation token counters on
  Prometheus /metrics; a T3-family scraper prices them against a
  GPU-hour-derived rate card (cost-per-token computed from the
  customer's node cost, not a provider price sheet) — tokenomics for
  enterprises running their OWN models, a surface no API-key tool
  covers. Needs a rate-card ruling (money-math discipline applies).
  Trigger: first customer running self-hosted inference.
- **AWS/Azure/GCP Marketplace listings + IaC templates (ARM/Bicep, CFN/CDK,
  Terraform)** — trigger: second enterprise deal, or first requiring
  marketplace procurement. Azure Marketplace private offers noted as future
  procurement channel. [R-MARKETPLACE a; R-ENTERPRISE-READY c]
- **Control-plane early access** — signup counts (landing CTA, R-GTM-CONTROL)
  are Phase-2 trigger evidence; weekly count in the daily digest.
  [Trigger registered, founder-approved 2026-07-22: 25 cumulative signups →
  founder notification line in the daily digest; that is the evidence bar
  for opening the Phase-2 conversation.]
- **CD / auto-deploy-on-tag** (R-DEPLOY-AUTOMATION 2) — trigger: (a) >1 app
  ships from the monorepo (post WP-PLAT-0), OR (b) deploy frequency exceeds
  1/week for a month. Until then deploys are founder-initiated, ONE command
  (scripts/provision.sh / deploy/tf, WP-DEPLOY-1), human-observed.
- **Concierge onboarding** (R-MAGIC-CONNECT 2026-07-22 §4) — GTM register,
  NOT a build item: for early customers, "book 10 minutes, we do it on a
  call with you". The solo-founder advantage incumbents cannot match.
  [Limit registered, founder-approved 2026-07-22: >5 new paying customers
  in any week = the call stops scaling → onboarding automation becomes a
  build item.]
- **Org-level source identity** (R-MULTI-SOURCE 2026-07-23, honest limit) —
  the same-key fingerprint guard cannot catch two DIFFERENT admin keys of
  the SAME provider org (double-count risk stays open by that path).
  Hardening = fetch the org id during wizard validation and enforce
  uniqueness per (provider, org). Trigger: first support incident of a
  double-connected org, or the provider-OAuth item below firing (OAuth
  grants carry org identity for free).
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
  quality caveat attached. The services bridge. [Trigger registered,
  founder-approved 2026-07-22: rides the D7 export-candidate detector's own
  trigger (day-45 gate or first pattern-exhibiting customer) — one event,
  two deliverables.]
- **TASK DECLARATION layer** (R-INTENT-LADDER 2026-07-22 c) — optional
  route/tag purpose declarations via config or dashboard; detectors consume
  them to sharpen findings (task-tier mismatch, declared-repetitive → D7
  priority, budget-per-purpose). Declarations are counts-safe metadata —
  FR-22 untouched. [Trigger registered, founder-approved 2026-07-22: the T4
  STREAM spec conversations (declaration is a streaming-era config surface);
  promotion still needs a PRD amendment per the INTENT LAW.]
- **WP-SKILL** — SUPERSEDED 2026-07-23 by R-CC-LINK. Folded into WP-CC-LINK
  below as step 2 of the one-command install; the skill is no longer a
  separate deliverable, because shipping it alone would have asked a customer
  to run one command for the skill and another for the collector. Its ZTA
  credential (zero inference beyond invocation) carries over intact.
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
- **"Night Audit" mood — BACKLOG-DESIGNED, not someday** (R-DESIGN-TOKENS-2 §2,
  2026-07-25) — dark mood for on-call operators watching alerts. Promoted from
  someday to designed: because moods are value swaps over the role map, shipping
  it is a sibling `[data-mood="night-audit"]` value block plus an AA
  re-verification pass, with ZERO component changes by construction. The
  architecture landed 2026-07-25; only the values and the contrast audit remain.
  [Trigger registered, founder-approved 2026-07-22: first on-call/ops
  customer request — ships as one value block + AA pass, zero component
  changes by construction.]
- **Indic locales** (R-DESIGN-TOKENS-2 §6, 2026-07-25) — the translation-key
  layer ships with the wiring (en only). Adding a locale is then a catalogue,
  not a refactor, which is the entire reason the key layer goes in early.
  Bhasha-era synergy. [Trigger registered, founder-approved 2026-07-22:
  India-billed accounts reach 25% of the paying base, OR the first explicit
  hi-IN customer request — whichever first.]
- **Dark mode** (R-DESIGN 2026-07-20 §2) — LARGELY SUPERSEDED: the app
  shell ships the sanchaya/aura mood toggle (v1.5.1+), which IS dark mode
  for app surfaces. Remaining scope is a public-site toggle only.
  [Trigger registered, founder-approved 2026-07-22: first customer request
  for a dark public site.]
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

## WP-CC-LINK — CORE JOURNEY SHIPPED 2026-07-23 (see STATUS); residue below

SHIPPED: device-link + consent floor + ship→audit + machines UI + revoke +
cron helper. RESIDUE (packaging, this milestone's slice 2): PyPI publish
of `tokenops-cost-auditor` (founder-lane; R-NAMING correction 2026-07-23 —
NO short name, the full name IS the command), Claude Code skill
auto-install, pipx self-update path.

## WP-CC-LINK — one command, one consent (R-CC-LINK 2026-07-23)

CONSOLIDATES WP-SKILL and WP-COLLECTOR into a single subscriber deliverable.
They were two entries describing two halves of one install; a customer was
never going to run two commands. TRIGGER: immediately post-v1.5 launch,
est. 2-3 days.

    pipx install tokenops-cost-auditor && tokenops-cost-auditor link <code>
    [R-NAMING correction 2026-07-23: the register's original short-name
    command is superseded — full product name, everywhere, always]

Device-link pattern: the dashboard issues a short-lived code, the CLI
exchanges it for a scoped, revocable device token. NO KEYS ARE EVER TYPED —
the customer never handles a long-lived credential, and revocation is a
dashboard click rather than a key rotation.

That one command performs, in order:
1. CONSENT, in plain words, before anything else — what is collected (counts
   only), on what schedule, and how to revoke. Recorded in the audit log.
   Linking REFUSES to proceed without it.
2. Skill install into the customer's Claude Code. The skill invokes the LOCAL
   collector/CLI and performs zero inference beyond its own invocation — the
   ZTA credential, stated plainly in its README.
3. Collector arming: user-level scheduler, UAT-D5 dedup law (by request_id,
   max-complete usage wins, summary printed), counts-only by construction
   (FR-22 — no text ever read into the payload), shipped with FR-26 idempotent
   uploads.
4. A pipx self-update path, so the fleet does not rot.

LAW — ONE HUMAN ACTION IS THE FLOOR, NEVER ZERO (R-CC-LINK 2. Permanent.)
Remote or silent install is FORBIDDEN, as a matter of trust posture rather
than of technical difficulty. We are asking people to install an auditor
inside the agent holding their credentials; the moment that can happen
without them watching, the product is the thing it was built to protect
against. The consent screen is a FEATURE and is marketed as one: "you'll see
exactly what we collect before anything runs."

DASHBOARD (built at WP-CC-LINK build time, not before): Sources gains a
"Claude Code" source type — linked machines, last ship, revoke button.
Multi-machine is the same command per machine; fleet install uses the same
code, documented for team plans.

SDK/proxy note (R-CONNECT 3): remains Phase-2 control plane — X-01/X-02
intact for the audit product; recorded rationale: in-path components live
in the customer's VPC per the deployment contract, post-trust.

SDK/proxy note (R-CONNECT 3): remains Phase-2 control plane — X-01/X-02
intact for the audit product; recorded rationale: in-path components live
in the customer's VPC per the deployment contract, post-trust.

## Design-audit P3s (founder deep-audit order 2026-07-26; numbered per docs/design/DESIGN-AUDIT.md)

[Batch trigger registered, founder-approved 2026-07-22: F11-F16 fold into
WP-PIPELINE-UI / WP-REPORT-VISUAL — whichever first touches each item's
surface; none warrants its own round.]
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
- Public changelog page: docs backlog; CHANGELOG.md remains the record.
  [Trigger registered, founder-approved 2026-07-22: first post-launch docs
  batch (week 1-2 after the thread) — generated from CHANGELOG.md, no
  second record.]


## WP-REPORT-EXPLORER — PROMOTED + C1/C2 SHIPPED (R-EXPLORER PRD amendment 2026-07-23)

FR-32 promoted and built on the founder's direct order (same day): /explore
in the dashboard shell — filters date range, grouping, source tier, model,
finding type, severity, feedback status; ux mockup gated PASS-WITH-NOTES
before wiring; tests tests/test_explorer.py. RESIDUE PARKED: C3 saved named
views + "export this view" — HELD pending PLAN-FLYWHEEL §6 Q6 (export
partially fires the registered data-export trigger below; founder ruling
needed on whether it ships early or waits for that trigger).

## WP-PIPELINE-UI — FIRST post-launch gated milestone (R-PIPELINE-UI-SEQ, 2026-07-27)
Runs list (every audit: status, trigger, duration, expandable stage
timeline); per-stage drill-in (rows ingested vs rejected, priced vs
unpriced, per-detector ran/found-nothing honest-zeros evidence); connector
pull lineage (per-pull rows + failures, not just last_pull_at); alert
evaluation history ("checked, nothing crossed" — not only firings);
additive stage_events migration for real per-stage timings. Kit-composed
throughout (runs = table_open, timeline = ribbon rich form, live =
computing_label). Sequenced against WP-REPORT-VISUAL at day-45 by signal.
Pre-launch carve-out (live theater + row-errors download) shipped ahead of
it under R-PIPELINE-UI-SEQ.
- F16 (connect-first gate, 2026-07-27): wa-public.css carries raw px font
  sizes throughout; tokenize a public type scale next time the sheet is
  touched broadly.
- R-AGNOSTIC queue addition (founder walkthrough, 2026-07-27): Cursor and
  Lovable recorded as candidate AGG/T1 adapters — blocked today by the
  honest constraint that neither exposes a public usage/billing API; lands
  on (first customer request) AND (an export/API existing). Usage from
  these tools on customer-owned provider keys is ALREADY captured by the
  shipped T2 connectors — now stated on the landing.

- SDK atexit retention (S-1 cold re-gate note, 2026-07-23, non-blocking):
  each `init()` registers `Batcher.close` with atexit but never
  `atexit.unregister`s a prior closed instance, so a process that re-inits
  thousands of times retains that many small callbacks (object retention,
  not a thread/socket leak). One-line fix in `close()` when touched next.

- In-app "View report" link missing (system-tester O-0 gate, 2026-07-24,
  REACHABILITY — high value): no template anywhere links to /r/{token}
  (routes_report.py) — a signed-in user has no in-app click path to their own
  completed HTML/PDF report; delivery is email-only (the emailed signed URL).
  Same class as the unlinked-Anthropic bug (R-VERTICAL rule 9): shipped ≠
  reachable. The standing reachability law can't catch it because report pages
  aren't in tests/test_journeys.py APP_PAGES. Fix as a vertical slice: a "View
  report" affordance on completed audits (dashboard/runs/explore) → the signed
  URL, + a journey test walking to it, + add the report surface to the
  reachability inventory. NOT O-0-caused (pre-existing); surfaced by the
  whole-product gate. This is a distinct surface from tenancy, hence parked.

- OAuth authorize deep-link return (S-6 scope note, 2026-07-24): a
  logged-OUT user hitting /oauth/authorize sees a "sign in to authorize"
  interstitial linking to /login, but after login lands on /dashboard —
  they must reopen the app's authorize link. Polish: carry the authorize
  URL through login (a `next=` on /login honored by the verify redirect)
  so the consent screen returns automatically. Bounded out of S-6 to avoid
  auth-core surgery; the interstitial is honest in the meantime.

- [O-COH / R-Q6] Paused-source banner CTA. `metrics.has_live_feed` counts only
  `status=='active'`, so once R-Q6 downgrade-pause starts assigning `status=='paused'`,
  a workspace whose only source is paused (still LISTED on the Sources page,
  `!= 'revoked'`) will trip the data-coherence banner with a "Connect a source" CTA
  that's the wrong instruction — the right one is resume/upgrade. `paused` is not
  assigned anywhere in code today, so this is forward debt, not a live bug (cold
  O-COH f.4). When R-Q6 ships: branch the banner CTA on a paused-but-listed source.

- PLAIN-ENGLISH PDF REPORT (fast-follow of guided-first-run rev 2, founder
  walkthrough 2026-07-25). The in-app finding surfaces (Findings page, drawer,
  dashboard, first-run preview) now LEAD with a plain-English `summary` + keep
  the technical pointers. The downloadable PDF/web report (_report_body.html) does
  NOT yet — it is render-only and services-layer (render_report_html passes only
  the ReportModel; no web/help access), and the summary copy lives in the web help
  registry. NOT a scope addition — the same founder feedback, split for a clean
  layering fix: move the detector display copy (plain/summary) to a services-
  accessible source (e.g. services/rules or a services copy module that web/help
  reads), then carry it into the ReportModel at build time so web + PDF show the
  same plain-English without a layering break. Until then the report shows the
  finding id + fix_text as today.

- MORE FINDINGS / RICHER DETECTION (founder-chosen follow-up, 2026-07-25). Founder
  asked "why so few findings — it can be many, dynamic analysis." Root cause is
  understood and now stated honestly in-product: per-request logs (upload/SDK) run
  all 6 detectors PER ROUTE (many findings); connected provider usage APIs give
  coarse day×model aggregates so only D1/D2/D3 run (fewer). NOT a bug. The
  follow-up is to expand the analysis DEPTH: (a) more waste detectors (new
  patterns) — each needs a money-math golden per CLAUDE.md rule 4; (b) richer
  per-route / per-model breakdowns; (c) surface the aggregate-vs-per-request depth
  gap more prominently so users choose the deep path. Stays DETERMINISTIC (X-04 —
  no LLM narrative); "dynamic" = data-driven per-route, not ML. Founder said: ship
  the guided-first-run rev (plain-English + upload-primary) FIRST, then this.

- CROSS-AUDIT DRIFT — FOLLOW-UPS (after the Breakdown "vs your last audit" slice,
  2026-07-25). The drift view compares the four headline vitals across the two most
  recent audits. Natural extensions, each a clean deterministic slice: (a) DRIFT
  ALERTING — when an efficiency metric regresses beyond the material bar, surface it
  through the existing alerts/daily-digest channel (observe-only, X-02 — never
  enforcement) so a regression reaches the owner without them opening the page; (b)
  PER-MODEL / PER-ROUTE DRIFT — drill the trend into which model or route drove the
  regression (compare by_model / by_route slices across audits), not just the blended
  vitals; (c) MULTI-AUDIT TRENDLINE — a sparkline over the last N audits rather than a
  single prior comparison (needs a small history read). All stay DETERMINISTIC (X-04),
  diffs of already-priced tokenomics.json figures, FR-22 counts-only.
- "SIX DETECTORS" COPY IS STALE (surfaced during the D10 anomaly slice,
  2026-07-25). The engine now runs NINE detectors — d1-d6 (savings) + d8/d9/d10
  (informational: concentration, ineffective-cache flip, spend anomaly) — but the
  customer-facing copy still says "six detectors" in landing.html (x2),
  app/_first_run.html, app/findings.html, static/tour.js, docs-site/concepts/how-it-
  works.md and engineering/performance.md. Went stale when D8/D9 landed (PR #18) and
  D10 makes it staler. NOT a mechanical find-replace: needs a deliberate messaging
  decision that honestly distinguishes the six savings-finders (find avoidable
  spend) from the informational insights (point you where to look), validated to the
  ux gate — and it touches the just-retoned landing (#20), so it is its own small
  slice, not folded into an unrelated detector build. No test asserts "six", so
  nothing is broken today; this is an honesty/completeness refresh.

- ANOMALY DEPTH-ENGINE — NEXT SLICES (after D10, 2026-07-25). D10 ships DAILY
  within-audit spike detection. Natural follow-ups, each a clean deterministic
  vertical slice: (a) CROSS-AUDIT DRIFT — compare this audit's tokenomics.json
  vitals to the prior audit's (both now persisted) and flag efficiency REGRESSIONS
  (cost-per-1k-output up, cache-hit down, waste-share up); like-to-like over time,
  so precise; new finding/alert class; needs >=2 audits with the artifact (honest
  first-audit empty state). (b) INTRA-DAY / FINER GRANULARITY — hourly buckets so a
  single-day-dense upload (thousands of calls in one day) can still surface a spike
  (D10 needs >=7 days today; a one-day log is honestly dormant). (c) SEED THE SAMPLE
  with a multi-day planted spike so the first-run OUTPUT PREVIEW demonstrates the
  anomaly capability (the committed waste-pack spans 3 days → D10 dormant on it, so
  a new user does not see anomaly detection until they upload >=7 days; a seeded
  sample would demo it — but changes the sample figures, which ripples to
  test_guided_first_run / the preview, so it is a scoped follow-up, not a mid-slice
  edit). (d) DAY-OF-WEEK / SEASONAL BASELINE (cold-reviewer note on D10,
  2026-07-25): D10 uses a single window-wide median, so a LEGITIMATELY recurring
  heavy day (a scheduled weekly batch) re-flags every occurrence — honest today (the
  finding asks the user to VERIFY, and lists "a backfill" as an intended cause), but
  a day-of-week / seasonal baseline (compare Sundays to Sundays) would stop
  re-flagging a known pattern. All stay DETERMINISTIC (X-04), FR-22 counts-only.

- INFORMATIONAL FINDINGS — SURFACE THE PER-INCIDENT FIGURE (ux-reviewer note on D10,
  2026-07-25). Informational findings (D5/D8/D10) carry monthly_cost_impact_usd=0, so
  the drawer headline no longer shows a misleading "$0.00" (fixed in the D10 slice: it
  now shows an "Informational — no saving claimed" chip). But D10's genuinely useful
  per-incident number (the spike day's excess $, the multiple) currently lives only in
  the plain-English fix_text, not in a prominent structured slot, because FindingRow
  persists only {route, severity, monthly_impact, confidence, fix_text, evidence} — NOT
  the detector's detail{} dict. Follow-up: persist FindingRow.detail (a JSON column +
  migration) so the drawer can render an informational finding's key figure (excess $,
  multiple, spike day) prominently at depth (a)/(b) for BOTH audiences — a cross-cutting
  display change across all informational detectors, hence its own small slice with a
  ux pass, not folded into a detector build.

- RAZORPAY CALLBACK_URL FALLBACK (B5, Issue #74 noted follow-up). The Standard Checkout
  modal is an iframe; browsers that block third-party iframes (Instagram/FB Messenger/UC
  in-app browsers) can't complete it. Razorpay's `callback_url` redirect-based fallback
  covers those; not built this slice (the modal path covers standard browsers).
