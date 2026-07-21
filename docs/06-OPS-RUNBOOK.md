# Ops & Deployment Runbook — TokenOps Cost Auditor v1.0

## 1. Production topology (v1)

One VPS (4 vCPU / 8GB / 80GB SSD; Hetzner CX32-class or Oracle ARM
free-tier for staging). docker-compose stack:
- caddy (ports 80/443, auto-TLS, reverse proxy → app:8000)
- app (uvicorn, single worker — multi-worker uvicorn's keep-alive ping kills
  CPU-saturated workers on small VPS cores and orphans in-flight audits
  (D13 re-validation 2026-07-19); audit concurrency = MAX_CONCURRENT_AUDITS.
  Multi-worker returns only with the queue/workers BACKLOG item.
  Volume mounts uploads/, reports/)
- postgres:17 (compose-internal network only; volume pgdata)
- cron sidecar (ofelia or host crontab): purge daily 02:00 UTC,
  backup daily 02:30 UTC.
Domain: audit.<brand>.com. DNS A record → VPS. Staging = same compose on
Oracle box with APP_ENV=staging.

## 2. Deploy procedure (target < 30 min, NFR-09)

ONE-COMMAND PATH (WP-DEPLOY-1, R-DEPLOY-AUTOMATION): `deploy/tf` (Hetzner,
creates the VM) or `scripts/provision.sh --host <ip> --domain <d> --tag <t>`
(any Ubuntu host) executes steps 1-6 below automatically and prints the
smoke results; step 7 (CHANGELOG entry) and external DNS/healthz
verification stay manual. The numbered steps remain the reference and the
manual fallback.

1 provision VPS, hardened: ufw allow 22/80/443, fail2ban, non-root user,
SSH keys only. 2 install docker+compose plugin. 3 git clone repo;
`cp .env.example .env` fill secrets. 4 `docker compose up -d --build`.
5 `docker compose exec app alembic upgrade head`. 6 smoke: /healthz 200,
landing loads, magic-link email arrives, sample audit (F1 fixture) end to
end. 7 record deploy in CHANGELOG.
Rollback: `git checkout <prev-tag> && docker compose up -d --build`;
DB migrations are additive-only in v1 (policy) so no down-migration risk.

## 3. Observability

Logs: structlog JSON → docker json-file (max-size 50m, max-file 5);
`docker compose logs -f app` for live; ship to grafana-cloud free tier
(promtail) when >10 customers.
Errors: Sentry free tier via SENTRY_DSN.
Health: /healthz (db ping, disk_free_mb); UptimeRobot free monitor 5-min
interval → email+phone.
Business metrics (v1 = SQL, not dashboards): daily cron emails founder:
audits run, revenue marked, purge count, failures. Script
scripts/daily_digest.py.
Alert conditions: healthz down 2 checks; any audit status=failed; disk
>80%; backup absent >26h (checker in digest).

## 3a. Activation steps — payments + federation (founder-owned credentials)

The CODE for both ships dark until credentials exist; no dashboard step here
requires a deploy.

PAYMENTS (FR-18/R-Q11 link+webhook design, already implemented):
1 Stripe: create a Payment Link per plan (Pro/Scale monthly), copy webhook
  signing secret → .env STRIPE_PAYMENT_LINK_URL / STRIPE_WEBHOOK_SECRET;
  point the webhook at /api/v1/webhooks/stripe. 2 Razorpay: same shape →
  RAZORPAY_* vars, webhook /api/v1/webhooks/razorpay. 3 `docker compose up
  -d` re-reads .env; the billing page switches from "Checkout opens once
  billing is switched on" to live Pay links automatically. Until then,
  admin mark-paid (Q8) remains the manual fulfillment path.

GOOGLE SIGN-IN (federation, 2026-07-27):
1 console.cloud.google.com → OAuth client (web), authorized redirect URI
  https://tokenops.cloud/auth/google/callback. 2 .env GOOGLE_CLIENT_ID /
  GOOGLE_CLIENT_SECRET; restart. 3 The "Continue with Google" button renders
  on /login + /signup only once configured (dead buttons are promises).

## 3b. Status page (R-SAAS-BASICS 3)

status.tokenops.cloud = UptimeRobot public status page. Founder-dashboard
steps (no UptimeRobot/DNS credential lives in this repo or on the box):
1 UptimeRobot -> Status Pages -> create public page from the existing
  healthz monitor. 2 Set custom domain status.tokenops.cloud; UptimeRobot
  shows the CNAME target. 3 At the DNS provider add
  CNAME status -> <target from step 2>. 4 Verify https://status.tokenops.cloud
  serves the page; the site footer already links it.

## 4. Backup & restore (NFR-08)

Backup: scripts/backup.sh — pg_dump -Fc → /backups/tokenops_%F.dump,
rotate 14 days, rclone copy to object storage (B2/R2 free tier).
Reports/ snapshotted same job as reports_%F.tar.gz (the postgres image has
no rsync; the script uses rsync only if the base image ever gains it).
Uploads/ NOT backed up (they purge — data-policy consistency).
Restore drill (monthly, logged in this file): restore latest dump to
staging postgres, run smoke audit, record time + result below.
Restore log: (append entries here)

- 2026-07-17 (D10 exit drill, T-OPS-01/02) — 07:59:14Z→08:00:42Z UTC (88s
  total). Primary postgres:17 container: alembic 001+002 applied, smoke audit
  on F1 fixture (openai_small.jsonl) ran to done ($3.233777785, PDF 55KB).
  scripts/backup.sh executed INSIDE the container as ofelia would:
  tokenops_2026-07-17.dump (28K, pg_dump -Fc) + reports_2026-07-17.tar.gz
  (tar fallback path exercised — no rsync in postgres image). pg_restore
  --no-owner into a fresh staging postgres:17: row counts identical
  (audits=1, findings=8, audit_log=2, users=1) and a NEW smoke audit against
  the RESTORED db completed status=done with identical spend (deterministic
  engine). Result: PASS. Note: postgres containers accept connections during
  initdb's temp-server phase — wait for two pg_isready checks 2s apart
  before restoring.

## 5. Security ops

Secrets only in .env (chmod 600) — never in repo; SECRET_KEY 64B random.
Dependency updates: `uv lock --upgrade` weekly + CI green before deploy.
Upload handling: content-sniff, size cap, stored non-executable path.
Admin token rotation on any suspicion; admin actions all in audit_log.
Data policy enforcement: purge cron + T-LIF tests; manual purge button.
Incident playbook: (a) take app down `docker compose stop app` (Caddy
serves maintenance page), (b) snapshot logs, (c) rotate secrets,
(d) postmortem note in this file.

## 6. Cost sheet (monthly, v1)

VPS ~ ₹1,600 · domain amortized ~ ₹100 · email (SMTP free tier / SES
pennies) · Sentry/UptimeRobot/R2 free tiers · TOTAL < ₹2,000/mo.
No inference cost by design (NFR-01).

## 7. SaaS subsystem checklist (v1 status)

Auth: magic-link ✔ (SSO = Phase 2) · Billing: payment links + webhook ✔
(subscriptions = Phase 2) · Emails: transactional ✔ · Admin: ✔ ·
Audit log: ✔ · Rate limiting: ✔ · Backups: ✔ · Monitoring: ✔ ·
Data retention: ✔ automated · Legal: ToS + Privacy + DPA-lite pages
(templates day 8) · Status page: UptimeRobot public page (free).

## 8a. Detector threshold knobs (UAT calibration reference; added D11-12 prep)

Every detector threshold is an env-tunable Settings field (config.py). When
UAT feedback says a detector over/under-fires, turn the matching knob — never
edit detector code for calibration. Golden tests pin behavior at DEFAULTS; a
default change is money-math discipline (CLAUDE.md rule 4: golden update +
spreadsheet diff in the same commit).

| Env var | Default | Effect | Turn when UAT says |
|---|---|---|---|
| D1_SHORT_COMPLETION_T | 150 | completion p50 below this = "short/mechanical" bucket | D1 flags real reasoning routes -> lower; misses obvious gluework -> raise |
| D2_CACHE_MIN_REPEATS | 25 | min identical-prefix repeats before a cache finding | noisy tiny groups -> raise |
| D2_CACHE_MIN_PROMPT_TOKENS | 1024 | ignore prefixes shorter than this | trivial-prefix findings -> raise |
| D2_SUFFIX_HAIRCUT | 0.8 | cacheable fraction without hash evidence (R-Q5) | — money-math default; golden discipline applies |
| D2_TTL_WINDOW_S / D2_TTL_WINDOWS | 300 / {anthropic:300, gpt-5.6:1800} | cache-lifetime window per family (C4) | only on provider TTL changes, with source |
| D2_NO_WINDOW_HAIRCUT | 0.7 | haircut when writes can't be estimated | — money-math default |
| D3_BLOAT_MULT | 2.0 | route p90 prompt vs corpus bin median multiplier | lean routes flagged -> raise; obvious bloat missed -> lower |
| D4_WINDOW_S | 120 | retry-cluster anchor window | slow retries missed -> raise; scheduled jobs clustered -> lower |
| D4_DUP_MIN | 3 | min identical calls to call it a storm | pairs are noise -> raise |
| D5_MAX_RATIO | 4.0 | declared max_tokens >= N x completion p95 | pedantic flags -> raise |
| D5_RESERVED_BILLING | false | price D5 findings (only if account reserves capacity) | set true only with billing evidence |
| D6_LOOP_MIN | 8 | min calls in a run to consider it a loop | short tool bursts flagged -> raise |
| D6_BATCH_SZ | 5 | modeled batching factor for savings | — money-math default |
| D6_SMALL_COMPLETION_T | 300 | loop calls have completions under this | verbose agents missed -> raise |
| D6_RUN_WINDOW_S / D6_SESSION_GAP_S | 600 / 900 | run anchor / session split | slow agents missed -> raise window |
| D6_REREAD_MIN | 5 | same prefix_hash >= N in session = re-read signature | hash-poor exports -> lower with care |
| PREFIX_HASH_CHARS | 4096 | prefix identity span (R-Q6) | never per-customer; contract constant |

## 8b. Break-and-fix drills (WP-COMPREHEND; after D13, STAGING ONLY — never prod)

One scripted drill per week for 5 weeks. The operator (Claude Code session)
introduces ONE catalogued fault on staging; the founder diagnoses using ONLY
DEBUGGING-PLAYBOOK.md and logs — no AI assistance — then verifies the fix
with the test suite. Acceptance bar: 4 of 5 diagnosed unassisted.

Fault catalogue (introduce exactly as scripted; restore staging after):
- DRILL-1 wedge the queue: set MAX_CONCURRENT_AUDITS=1 and start a
  never-finishing audit (oversized fixture), then submit a real one.
  (Playbook entry 2.)
- DRILL-2 break a parser: corrupt 10% of rows in a staged upload so the
  95% rule trips. (Entry 3 / entry 1.)
- DRILL-3 rotate the webhook secret on ONE side only, then replay a valid
  payment event. (Entry 6.)
- DRILL-4 disable the ofelia purge job (comment it out, restart sidecar)
  with a backdated audit present. (Entry 7.)
- DRILL-5 stop postgres. (Entry 8.)

Drill log (append: date · drill · diagnosed-unassisted? · time-to-diagnosis
· notes):
- (entries here)

## 8. Launch-week ops cadence

Daily: digest email review (5 min), failed-audit triage, backup check.
Weekly: dependency bump, restore drill (first month), pricing.yaml
refresh vs provider price pages (versioned commit).
