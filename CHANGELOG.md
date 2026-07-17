# CHANGELOG — deploys and releases (runbook §2 step 7)

Format: date UTC · tag/commit · what · smoke result. Deploy entries are
appended by the person deploying, same day.

(entries append below)

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
