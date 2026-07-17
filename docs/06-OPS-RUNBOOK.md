# Ops & Deployment Runbook — TokenOps Cost Auditor v1.0

## 1. Production topology (v1)

One VPS (4 vCPU / 8GB / 80GB SSD; Hetzner CX32-class or Oracle ARM
free-tier for staging). docker-compose stack:
- caddy (ports 80/443, auto-TLS, reverse proxy → app:8000)
- app (uvicorn, 2 workers; volume mounts uploads/, reports/)
- postgres:17 (compose-internal network only; volume pgdata)
- cron sidecar (ofelia or host crontab): purge daily 02:00 UTC,
  backup daily 02:30 UTC.
Domain: audit.<brand>.com. DNS A record → VPS. Staging = same compose on
Oracle box with APP_ENV=staging.

## 2. Deploy procedure (target < 30 min, NFR-09)

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

## 4. Backup & restore (NFR-08)

Backup: scripts/backup.sh — pg_dump -Fc → /backups/tokenops_%F.dump,
rotate 14 days, rclone copy to object storage (B2/R2 free tier).
Reports/ directory rsynced same job. Uploads/ NOT backed up (they purge —
data-policy consistency).
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

## 8. Launch-week ops cadence

Daily: digest email review (5 min), failed-audit triage, backup check.
Weekly: dependency bump, restore drill (first month), pricing.yaml
refresh vs provider price pages (versioned commit).
