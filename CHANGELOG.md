# CHANGELOG — deploys and releases (runbook §2 step 7)

Format: date UTC · tag/commit · what · smoke result. Deploy entries are
appended by the person deploying, same day.

(entries append below)

- 2026-07-23 · v15-d10 (pre-tag rehearsal, NOT a deploy) · V-D10 DEPLOY
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
  volumes destroyed afterwards. NO PRODUCTION DEPLOY: that remains a
  separate founder GO after the gates.

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
