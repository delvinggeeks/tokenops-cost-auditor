# CHANGELOG — deploys and releases (runbook §2 step 7)

Format: date UTC · tag/commit · what · smoke result. Deploy entries are
appended by the person deploying, same day.

(entries append below)

- 2026-07-22 · v1.5.15 (073b5dd) · COMPLETENESS SWEEP + R-ARCH-PATTERNS(a)
  live. Founder order "implement everything planned, miss nothing" → three
  parallel record sweeps (FR/NFR vs traceability; all §0.1 rulings vs the
  deploy ledger; BACKLOG/flywheel trigger register). Verdict: v1.5 ruled
  set fully shipped; ONE gap found and closed same-day — the docs-site
  Architecture-principles cited-claims section (zero-token, zero-trust
  five axes, five-gate validation ladder; sales line stays
  registered-not-released). FR-31 traceability row now records its ruled
  deferral to WP-PIPELINE-UI. launch/FEATURE-INVENTORY.md = the full
  punch-card incl. override menu + parked-without-trigger list. SMOKE
  PASS: docs.tokenops.cloud/engineering/architecture/ 200, new section
  serving (7 marker hits). Static-docs deploy — app containers untouched.

- 2026-07-22 · v1.5.14 (fc3b9eb) · R-PRICING-FINAL-2 + R-DAILY-LOOP live.
  Dual-market pricing after five founder amendment rounds and verified
  India research: global Pro $19 launch → $29 list, Scale $59 → $99;
  India Pro ₹499 → ₹999 incl GST, Scale ₹14,999 flat; one-shots
  $500/₹20,000. First-200 launch cohort PER MARKET, grandfathered; flip
  computed in code from the append-only activation ledger (cold-review
  caught the mutable-row market-switch hole). One currency per view, no
  mixing (test-pinned); spend gates + qualifying line + anchor line.
  Daily loop: per-customer daily digest (audit-identical rate math,
  $10.50 cached-token golden), staged 50/80/100% budget alerts,
  dashboard Yesterday tile; migration 008 applied in prod (runbook step
  5 — first schema change since d3f8a1c7e604). Gates: cold
  PASS-WITH-NOTES + vv PASS-WITH-NOTES, all five findings fixed
  in-round and test-pinned. SMOKE PASS: healthz ok, USD view
  $19/$29/$59/$99 + launch notes with zero ₹ prices, INR view
  ₹499/₹999/₹14,999/₹20,000 + GST line with zero $ prices,
  alembic_version=a9d24c8e7f31.

- 2026-07-21 · v1.5.13 (3e45159) · FEDERATION MAJORS live (R-FED-MAJORS —
  founder: "why only Google"). The Google route pair generalized to a
  FEDERATIONS registry; Microsoft (Entra v2 common — work/school +
  personal) and GitHub (OAuth2 + verified /user/emails) join Google. One
  shared login path keeps the R-FREE-CONNECT one-meter law through every
  door; each provider gates independently on its FULL credential pair
  (id-without-secret stays dark). Cold-review PASS-WITH-NOTES; all three
  notes fixed in-round and test-pinned: cookie-pinned OAuth state (CSRF
  hardening over signature-only), server-side logging of exchange
  failures, full-pair gating. Apple recorded as a BACKLOG trigger
  (private-relay vs work-email identity); SAML/Okta stays X-03.
  Activation per provider: runbook §3a. SMOKE PASS: healthz ok, 0 buttons
  rendered (nothing configured), unconfigured routes 404, /auth/verify
  not shadowed, landing 200.

- 2026-07-21 · v1.5.12 (8c378a3) · R-FREE-CONNECT + FEDERATION live. Free
  now truly starts free: signup grants the single comp credit (the marketed
  free audit had been UNWIRED — it 402'd at the payment gate; found while
  drafting the ruling, closed by test), Free connects ONE source whose
  first-pull audit shares that one meter with uploads, the scheduler
  excludes Free from pulls and audits (plan-based; dunning accounts keep
  pulling per R-Q12). Google sign-in shipped config-gated (no client id =
  no button; activation = runbook §3a, founder credentials). Payments were
  already implemented as link+webhook — activation steps documented; the
  billing page goes live the moment .env carries the links. Pricing
  research (103-agent verified run) delivered launch/PRICING-PROPOSAL.md:
  current $99/$299 sit at the FinOps 1-3%-of-spend norm; ruling options
  A/B/C await the founder. Gate clean PASS. SMOKE PASS.

- 2026-07-21 · v1.5.11 (e15800c) · TOOL-COVERAGE LINE live: Cursor/Lovable
  checked against the record — in NO spec; R-AGNOSTIC (founder's own law)
  pull-sequences tool adapters and neither exposes a usage API. The TRUE
  claim ships: tools on customer keys (Claude Code, Codex, Cursor,
  LangChain) land in provider usage automatically — one connection covers
  all. Both queued in BACKLOG under R-AGNOSTIC with the honest constraint.
  SMOKE PASS.

- 2026-07-21 · v1.5.10 (b0f1618) · CONNECT-ONLY MARKETING live (founder
  ruling, round 7): upload leaves the pitch — hero and workflow speak
  business language (connect your account, the platform does everything
  else), the free path reframed jargon-free ('drop in a usage file — we
  show you exactly where to get it'), Free blurb de-jargoned everywhere it
  renders. Upload stays fully shipped as the option behind /upload. Gate
  PASS-WITH-NOTES (its FR-23 note was grep scope — the string lives in the
  shared shell footer; the rendered-page test is green). SMOKE PASS.

- 2026-07-21 · v1.5.9 (f8b629d) · CONNECT-FIRST LANDING live (walkthrough
  round 6). Founder challenged upload-led marketing as off-spec; the RECORD
  showed the platform per spec (X-01/X-02 forbid in-path components;
  R-CONNECT wizard shipped; upload IS the Free tier + six-detector path) —
  the landing's EMPHASIS was the real gap. Hero now leads free-audit-then-
  connect-on-Pro; connector cards sell the shipped wizard with the plan
  DISCLOSED (first gate attempt FAILED on exactly that omission — fixed,
  re-gated PASS); architecture section states the enterprise infra answer:
  managed cloud outside your VPC, read-only in, findings out, nothing in
  the request path. SMOKE PASS. Walkthrough resumes.

- 2026-07-21 · v1.5.8 (d38f17a) · 3D WORKFLOW + ENTERPRISE NAV + SPLIT AUTH
  live (walkthrough round 5). C10 money pulse travels the workflow's flow
  line through perspective stage cards — loops twice then rests (speced
  before code); header gains real destinations (How it works / Pricing /
  Docs / Sample report); /login + /signup rebuilt as enterprise split-screen
  with the aura brand panel — NO SSO buttons (ruled X-03 absence; dead
  buttons are promises). T-POL-01 ordering preserved on the /upload teaching
  variant; /signup sheds the tabs (jobs split). Gate PASS-WITH-NOTES; its
  stale-evidence note closed with asserted re-captures. One process slip
  owned: a commit briefly landed on a red suite because the shell chain
  gated on ruff, not pytest — caught same-turn, closed green before ship.
  SMOKE PASS. Walkthrough resumes.

- 2026-07-21 · v1.5.7 (4fb1a28) · MODERN-SAAS HERO live — walkthrough round
  4, self-judged against the live page and agreed with the founder. Full-
  bleed dark hero on aura's value sheet, centered 72px display headline,
  product shot large in a browser frame under the accent glow, float cards
  riding it, honest labels retained; schedule numbering removed. Two
  computed-style bugs fixed at cause: .pub-nav a out-specified .btn-primary
  (CTA text washed — now asserted white in capture) and the neumorphic white
  inset washed ALL saturated primary fills (--control-depth-primary token,
  both moods). Gate PASS-WITH-NOTES (note pre-closed by computed assertion).
  SMOKE PASS. Walkthrough resumes.

- 2026-07-21 · v1.5.6 (f6b045a) · versioning gate FAIL closed and re-gated
  PASS. The completeness gap (tour.js + og:image unversioned — the exact
  heuristic-cache hole) fixed and made STRUCTURAL: a rendered-page test now
  forbids any unversioned /static reference on landing/login/dashboard/
  findings, partials included. Redeployed; zero unversioned refs on the
  live landing.

- 2026-07-21 · v1.5.5 (cc4573f) · ASSET VERSIONING + HERO DEPTH SCENE live.
  ROOT CAUSE FOUND for "the landing never changed": static assets had NO
  Cache-Control, so the founder's walkthrough tab rendered two design
  deploys under stale css/js while every curl smoke fetched fresh. Fixed
  with content-hashed asset() URLs (bust on deploy by construction) +
  immutable caching for versioned assets. Round-3 asks shipped: layered
  hero depth scene (C9 speced first) with the fold's live figures floating
  as sample-data-labeled TYPE, tilt drives the whole scene; explicit
  problem statement opens Schedule 01. SMOKE PASS: versioned urls live,
  immutable cache-control on versioned assets, hero-scene markers, ONE cta,
  FR-23. Walkthrough resumes — a normal refresh now shows the real page.

- 2026-07-21 · v1.5.4 (651569d) · ENTERPRISE ELEVATION ROUND live — closes
  founder walkthrough punch round 2. Delving Geeks removed from every public
  surface (WitAura is the company; Terms entity line + docs mirror updated).
  The landing composes as an audit document: numbered Schedules (mono ledger
  eyebrows), every screenshot a labeled Exhibit, the dollar's-journey flow
  line through the five stages (C6), six detectors named plainly in a
  what-it-finds grid, designed comparison matrix with the double-rule
  verified row, the accountant's rule DRAWN under the measured 32.5% (C7),
  one orchestrated hero entrance (C8) — all three speced on the motion
  sheet before code. Gate: ux PASS-WITH-NOTES (scroll-fallback note closed;
  hero-fold money-figure note recorded for founder judgement). Budgets hold
  (JS 8,215B raw, pub css ~4.5KB gz). DEPLOY: backup, archive, rebuild,
  healthy in 8s. SMOKE PASS: healthz db:true; all schedule/exhibit/flow
  markers live; zero Delving Geeks matches on landing+terms; ONE cta; FR-23
  verbatim. Walkthrough resumes.

- 2026-07-21 · v1.5.3 (11f235b) · WITAURA BRANDING ROUND live — closes the
  founder walkthrough HOLD ("no WitAura branding, not enterprise grade").
  Product-led lockup per founder choice: WA monogram (ONE include; favicon
  mirrors with documented literals), hero eyebrow "AI spend governance · by
  WitAura", display-scale headline, trust proof chips, dark anchor band on
  aura's own value sheet (zero new colours; a rendering pass caught h3s
  inheriting body's computed ink and vanishing — the band now sets color
  from vars, computed rgb asserted), enterprise footer with WitAura company
  block + © line, favicon + OG/twitter meta. Gate: ux PASS-WITH-NOTES (mark
  single-sourcing note closed with a test). DEPLOY: backup, archive,
  rebuild, healthy in 9s. SMOKE PASS: healthz db:true; all brand markers
  live; ONE cta; FR-23 verbatim; favicon 200; budgets hold (html 4,595B gz,
  pub css 4,165B gz). Walkthrough resumes.

- 2026-07-21 · v1.5.2 (e8a552b) · DESIGN ROUND + SAAS BASICS + PIPELINE
  THEATER LIVE on https://tokenops.cloud. Ships: the founder deep-audit
  remediation (F1-F10 all confirmed fixed by founder verdict, evidence pairs
  in design/evidence/), R-STMT-GATING, R-SAAS-BASICS 1-3+4a (Scale rename
  with the no-Team ruled test, support affordance, status link, close
  account with typed-phrase consequence-in-words), and the R-PIPELINE-UI-SEQ
  carve-out (live pipeline theater with honest stage lighting + row-errors
  download; browser uploads land on the theater, JSON API unchanged). Gates:
  design-remediation ux PASS-WITH-NOTES (closed), theater ux PASS-WITH-NOTES
  (closed); 3b stranger smoke six-screenshot green. DEPLOY: backup first
  (tokenops_2026-07-21.dump 4.1M), git archive -> rebuild -> alembic audible
  no-op at d3f8a1c7e604, app healthy in 15s. SMOKE ALL PASS over real
  DNS/TLS: healthz db:true; landing FR-23 verbatim + ONE cta + support +
  status links + Scale (zero \bTeam\b matches on landing+terms); funnel
  routes 200; auth-gated 401 incl. the theater endpoints; close-account
  shipped on box; REAL Postmark magic link sent to the founder (mail.sent
  logged). Hardware: disk 11%, mem ~1GB used of 7.9GB. Founder-owned before
  the thread: UptimeRobot page + CNAME for status.tokenops.cloud. NEXT GATE:
  founder production walkthrough — punch list by number, ACCEPT/HOLD.

- 2026-07-21 · v1.5.1 (1b0c0b6) · UNIFIED UI + LANDING LIVE on
  https://tokenops.cloud. Ships the R-LOOK-FINAL execution block end to end:
  component kit + three signatures, §5 server-authority laws (alerts
  plan-gated with honest upsell; explicit-confirm with consequence-in-words
  on Applied/revoke/purge), §6 i18n key layer (en), all 7 screens composed
  onto the kit, aura mood behind the topbar toggle, magic link lands on
  /dashboard, R-STMT-GATING (archive always; email Pro/Team always, Free on
  activity months), and the R-LANDING-2 landing (nine sections, sanchaya,
  base.html deleted). Gates: wiring ux/vv/cold all PASS-WITH-NOTES (notes
  closed same-day); landing ux PASS-WITH-NOTES (sheet notes closed).
  Browser-verified before ship: confirm asks fire/decline/accept on the real
  findings page (which previously recorded verdicts NOWHERE — hx-target bug
  found by driving the page), double rule no longer strikes the verified
  figure, End-jump leaves no landing voids, phone clean, stranger path
  landing→signup→link→dashboard→tour green. DEPLOY: backup first
  (tokenops_2026-07-21.dump 4.1M + reports snapshot), git archive → rebuild
  → alembic no-op (head d3f8a1c7e604 unchanged, audible), app healthy.
  SMOKE ALL PASS over real DNS/TLS: healthz 200 db:true; landing 200 with
  FR-23 verbatim, ONE cta, released §5 header, attributed stats; funnel
  routes 200; auth-gated 401; budgets measured on prod: css 12,697B js
  2,358B hero 95,004B total 203,207B (all under 25.6K/15.36K/122.88K/307.2K).
  REAL Postmark magic link sent to the founder address (mail.sent logged;
  inbox receipt closes at the founder walkthrough). Next gate: FOUNDER
  PRODUCTION WALKTHROUGH — the program's final gate; launch thread posts
  only on founder ACCEPT.

- 2026-07-24 · v1.5.0 (35ad41d) · v1.5 MONITOR LIVE on https://tokenops.cloud.
  PRE-FLIGHT CAUGHT A FALSE PREMISE: the deploy order specified an incremental
  migration "001->007 (rehearsed)", but production stood at 002 (9 tables) with
  live data (3 users, 4 audits, 452 aggregates, 15,022 findings) — so the real
  path was FIVE unrehearsed migrations over customer data, not the one
  rehearsed. Paused and reported instead of executing literally (now permanent
  law R-PREMISE-CHECK). Also declined the one-command provision.sh path, whose
  steps 4-5 migrate production automatically with no rehearsal gate, and
  declined to copy the production dump off-box to rehearse locally (it holds
  real user emails). REHEARSAL ON-BOX: backup taken first
  (tokenops_2026-07-20.dump, 4.0M), restored into a throwaway `prodcopy` in
  the same postgres, 002->007 run against a byte-faithful copy of live data —
  all 15,022 findings / 452 aggregates / 4 audits / 3 users unchanged, tables
  9->16; prodcopy dropped immediately rather than left lying around. NULL
  semantics verified conservative and ratified as final: findings.route NULL
  on legacy rows falls back to finding_id so legacy findings can never be
  wrongly credited, and audits.observed_days NULL fails the MIN_VERIFY_DAYS
  gate — honest zeros, no backfill. DEPLOY: migrate 002->007 (additive, so the
  running old image tolerated the new schema), then `up -d` onto the new image;
  head d3f8a1c7e604. SMOKE ALL PASS: healthz 200 db:true (internal AND external
  over real DNS/TLS, cert valid to 2026-10-17); landing 200 with FR-23
  verbatim; /sample 200; /legal/terms renders $500 · ₹45,000 from the price
  config; auth-gated /dashboard,/sources,/billing correctly 401; REAL Postmark
  magic link accepted for delivery to lokesh@tokenops.cloud (mail.sent logged,
  request_id d5c7f270efec432d); engine end-to-end through the real detectors
  (17 calls, 2 findings, deterministic spend). HARDWARE RE-CHECKS: 4 vCPU,
  load 0.23, 933Mi/7.8Gi memory used, 9.2G/96G disk (10%), app 210MB RSS at
  0.29% CPU — ample headroom. NOT YET CONFIRMED: that the magic link ARRIVED
  in the inbox; SMTP acceptance is not delivery, and the founder's production
  walkthrough is what closes that.

- 2026-07-23 · v15-d10 @ ec50ca0 (pre-tag rehearsal, NOT a deploy) · V-D10 DEPLOY
  REHEARSAL on a production-shaped copy. Real topology, isolated: the live
  local stack was already up with populated pgdata/uploads/reports volumes,
  so the rehearsal ran as a separate compose project (tokenops-rehearsal)
  with its own volumes, renamed containers and loopback-only ports — the
  running stack was never recreated. postgres:17, same Dockerfile build,
  APP_ENV=prod, dummy secrets only (the real .env with the Postmark token
  was never read). MIGRATION CHAIN: full 001->007 applied from empty on real
  Postgres, each revision reporting by name; head = d3f8a1c7e604 (007
  statement email preference); 16 tables. NOTE: the standing order said
  "001->006" — the chain runs to 007, and 007 creates the statement-email
  preference the V-D7 settings path writes to. SMOKE: /healthz 200 db:true;
  landing 200 with FR-23 verbatim; /legal/terms renders $500 · ₹45,000 from
  the price config; /sample 200. SUITE: full suite green against Postgres
  with ZERO skips — the postgres-gated integration test that skips in every
  local run executed here and passed, exercising the with_for_update row
  locks that are no-ops on SQLite. FR-22 verified against the deployed
  schema: no prompt/completion text column exists (only token counts and our
  own findings.fix_text / statements.body_text). THREE DEFECTS FOUND AND
  FIXED: (1) Terms of Service quoted ₹20,000/audit while billing charges
  ₹45,000, and its guard test pinned both mirrors to the stale literal;
  (2) `alembic upgrade head` — runbook §2 step 5, the riskiest deploy step —
  printed nothing at all, because env.py never applied alembic.ini's logging
  config, leaving an operator unable to tell 7 applied revisions from a
  no-op; (3) alembic path_separator deprecation pinned. Rehearsal stack and
  volumes destroyed afterwards.
  SECOND PASS (this commit), after the ops gate flagged that pass 1 only ever
  migrated from empty: rehearsed the INCREMENTAL path a real deploy takes —
  migrated to 006 (production's current revision), wrote live user + statement
  rows at that schema, then ran `alembic upgrade head` over them. 007 applied,
  every live row survived byte-intact, and the new users.statement_emails
  column lands NULL on pre-existing rows, which both read sites deliberately
  treat as opted-IN (routes_settings.py:66, scripts/monthly_statements.py:54,
  matching 007's docstring) — so existing customers keep receiving statements
  after the deploy rather than being silently opted out. This pass also caught
  a defect in the pass-1 logging fix (see below).
  KNOWN GAPS, not covered by either pass and not claimed: (a) an in-place
  `up -d --build` over an already-running stack — container_name is pinned
  globally, and rehearsing that locally would have meant recreating the live
  stack; (b) magic-link delivery, since the rehearsal ran on dummy secrets
  with the real Postmark token deliberately unread.
  NO PRODUCTION DEPLOY: that remains a separate founder GO after the gates.

- 2026-07-19 · d13-live → d13-live.1 (8bd96a6) · FIRST PRODUCTION DEPLOY —
  https://tokenops.cloud on founder VPS (Contabo Cloud VPS 4: x86, 4 vCPU,
  7.8 GiB, Ubuntu 24.04, 169.58.44.80) via `scripts/provision.sh` one-command
  path. Three runs: initial (hardened first: ufw 22/80/443, password auth
  off, fail2ban; died at smoke), re-run proving idempotence (.env kept,
  postgres untouched), redeploy at d13-live.1. Two defects found by the
  physical deploy, fixed same day: (1) smoke probed https://localhost,
  which has no Caddy site once DOMAIN is real — curl exit 35 → SNI-correct
  `--resolve` probes (d33263b); (2) uvicorn multiprocess supervisor's 5s
  keep-alive ping replaced CPU-saturated workers on 4 vCPU and orphaned
  in-flight audits ("Child process died" ×2, OOMKilled=false, no kernel
  OOM) → `--workers 1` (8bd96a6; NFR-13 cap still bounds audit
  concurrency). SMOKE ALL PASS: healthz db:true; landing control
  narrative; magic-link 200 with REAL Postmark send (mail.sent, sender
  noreply@tokenops.cloud); ofelia 3 jobs; docs-site 200; www 301; external
  TLS = Let's Encrypt on apex + www + docs. HW RE-VALIDATION (this box):
  2 × 195 MB / 1.3M-row audits CONCURRENT → both done 34m20s wall, peak
  app 5.14 GiB + pg 150 MiB of 7.8 GiB, zero deaths post-fix; single 1M
  rows → 624 s, peak 2.25 GiB (dev-workstation refs: 2m48s / 94.3 s —
  4-vCPU box ≈ 7-12× slower, completes correctly); F1 end-to-end upload →
  done → web report 200 → PDF valid. Perf audits purged after measurement
  (uploads dir 0). Payments env-gated OFF for launch week. Open knob:
  DIGEST_TO unset (digest to stdout) — founder to choose address.

- 2026-07-17 · d13-deploy branch (post-UAT-1 sign-off) · FULL DEPLOY REHEARSAL
  on dev workstation — real compose stack (caddy auto-TLS → app → postgres +
  ofelia), runbook §2 steps 3-7 executed verbatim: .env from example with
  generated secrets (chmod 600), `docker compose up -d --build`, `alembic
  upgrade head` in-container, smoke ALL PASS (healthz 200 w/ db:true via
  Caddy TLS; landing serves control narrative + early-access CTA; magic-link
  issued (log adapter — no SMTP configured), verified 303 + session cookie;
  comp credit via admin; F1 upload 201 → status done → web report 200 → PDF
  200 valid). Ofelia registered purge/backup/digest with correct schedules;
  backup.sh + purge + digest each executed in-stack. CONCURRENCY CHECK
  (R-SEQ-POST-SIGNOFF): 2 × 195MB / 1.3M-row audits uploaded concurrently,
  both done in 2m48s wall; peak memory app 4,776 MiB + postgres 93 MiB =
  4.9 GB vs 8 GB VPS budget — PASS. PENDING: real VPS (hardware, domain,
  DNS, SMTP creds — founder-provided); perf + memory numbers to be
  re-validated on VPS hardware at actual deploy, per this entry.
