# DEBUGGING-PLAYBOOK.md — the 2am manual

For the founder, solo, production misbehaving (WP-COMPREHEND). Work top to
bottom inside each entry: symptom → look → reproduce → pin → stop rule.
Log lines are structured JSON — grep the `"event"` value shown.

## The three universal commands (copy-paste)

```bash
# 1. live app logs
docker compose logs -f app

# 2. the test suite (any fix is real only when this is green)
uv run pytest -m "not perf"

# 3. database shell (production postgres, inside the compose network)
docker compose exec postgres psql -U tokenops_cost_auditor -d tokenops_cost_auditor
```

---

## 1. Upload rejected

- **Symptom**: customer gets 400/413/422 at upload; no audit row created.
- **Look**: response body `error.code` — `payload_too_large` (over 200 MB),
  `validation_error` / `bad_request` (unparseable). Logs: grep the
  `request_id` from the customer's error message. Format failures say
  exactly what was expected: `"OpenAI or Anthropic JSONL export, or a
  generic CSV per the export guide."`
- **Reproduce**: `uv run tokenops-cost-auditor audit tests/fixtures/mixed_dirty.jsonl`
  (dirty rows) or feed any non-JSONL file.
- **Pin**: add the failing line shape to `tests/test_ingest.py` (see
  `TestTING05ColumnMapping` for the pattern).
- **STOP** if a previously-working format now rejects — that's a parser
  regression, not customer error: full session.

## 2. Audit stuck in `queued`

- **Symptom**: status API returns `queued` with a `queue_position` that
  never falls.
- **Look**: `SELECT id, status, created_at FROM audits WHERE status IN
  ('queued','processing') ORDER BY created_at;` — two rows `processing`
  forever means both slots are wedged. Logs: `"runner.slot_timeout"`.
- **Reproduce**: set `MAX_CONCURRENT_AUDITS=1`, start a big audit
  (`scripts/gen_perf_fixture.py`), upload a second.
- **Pin**: `tests/test_api.py` queue-admission tests (T-API-06 pattern).
- **First aid**: admin re-run (`POST /admin/audits/{id}/rerun`) after the
  wedged audit is diagnosed. **STOP** if slots wedge twice in a day.

## 3. Audit `failed`

- **Symptom**: status `failed`; customer sees a short message.
- **Look**: `SELECT id, error FROM audits WHERE status='failed' ORDER BY
  created_at DESC LIMIT 5;` — `error` is the user-safe cause (e.g. under
  95% valid rows). Logs: `"runner.failed"` with `audit_id`; the full
  traceback (never shown to customers) is directly above it.
  `row_errors.csv` sits next to the upload in `uploads/<audit_id>/`.
- **Reproduce**: `mixed_dirty.jsonl` breaches the 95% rule locally.
- **Pin**: `tests/test_runner.py` failure-path tests.
- **STOP** if `error` is empty or the traceback points inside
  `services/rules/` or `services/pricing/` — money-math code: full session,
  never a live hotfix.

## 4. Savings number looks wrong

- **Symptom**: headline % or a finding's dollar figure fails your sniff test.
- **Look**: report JSON, not the PDF: `reports/<audit_id>/report.json` —
  check `summary.savings_pct` (capped at 100 by design), the finding's
  `evidence` rows, and `detail.runs`/`detail.clusters` arithmetic. Then
  `pricing.unpriced_models` — excluded models change totals.
- **Reproduce**: `uv run tokenops-cost-auditor audit tests/fixtures/waste_pack_anthropic.jsonl`
  — every expected number for this fixture is derived by hand in
  `tests/fixtures/pricing_golden_NOTES.md`.
- **Pin**: a new golden row: hand-compute in the NOTES sheet FIRST, then
  the test (CLAUDE.md rule 4 — golden update + spreadsheet diff, same
  commit).
- **STOP — always.** Wrong money is the one defect class never patched
  solo at 2am. Capture report.json + the input, write the NOTES-sheet
  arithmetic, full session. (Precedent: the 228% dogfood defect.)

## 5. PDF render error

- **Symptom**: web report loads; `/pdf` 404s or the file is corrupt.
- **Look**: logs for a traceback mentioning `weasyprint` or `render_pdf`;
  check `reports/<audit_id>/report.pdf` exists and starts with `%PDF`
  (`head -c 5`). Missing Pango libraries = container/image problem.
- **Reproduce**: `uv run pytest tests/test_report_web.py -k Pdf`.
- **Pin**: extend `TestTREP02Pdf` with the failing report shape.
- **STOP** if HTML renders but PDF crashes on ONE audit only — template edge
  case (huge strings, odd characters): full session.

## 6. Payment webhook ignored (customer paid, can't upload)

- **Symptom**: provider dashboard shows the payment; upload still 402.
- **Look**: webhook responses in provider dashboard — our `{"status":
  "ignored"}` means signature OK but unrecognized shape/stale timestamp;
  401 means signature failed (secret mismatch). Then:
  `SELECT provider, event_id, received_at FROM webhook_events ORDER BY
  received_at DESC LIMIT 5;` (did it arrive?) and
  `SELECT id, provider, amount, audit_id FROM payments WHERE audit_id IS
  NULL;` (credit granted but unconsumed?).
- **First aid**: `POST /admin/payments/mark-paid` (email, amount, currency,
  provider) — audit-logged, safe, unblocks the customer NOW.
- **Reproduce**: `tests/test_payments.py` HMAC fixtures (independent
  reference signatures).
- **Pin**: add the provider's actual payload shape to the parse tests.
- **STOP** after first-aid: signature failures mean secret rotation or
  provider payload drift — full session same day.

## 7. Purge didn't run

- **Symptom**: uploads older than 7 days still on disk (digest alert, or
  `ls uploads/`).
- **Look**: `docker compose logs ofelia | grep purge` (did the 02:00 job
  fire?). Then `SELECT ts, subject FROM audit_log WHERE action=
  'audit.purged' ORDER BY ts DESC LIMIT 5;` Manual run:
  `docker compose exec app python -m tokenops_cost_auditor.services.lifecycle.purge`
- **Reproduce**: `tests/test_lifecycle.py` (backdated audits).
- **Pin**: extend T-LIF tests with the missed case.
- **STOP — same day, always**: FR-23 is a public promise; run the manual
  purge first, diagnose ofelia second.

## 8. Container down / site unreachable

- **Symptom**: browser timeout, or `/healthz` non-200.
- **Look**: `docker compose ps` (which container?); `curl -sk
  https://localhost/healthz` → `{"ok":..,"db":..,"disk_free_mb":..}` —
  `db:false` = postgres; low `disk_free_mb` = disk full (backups/uploads);
  app `Restarting` = crash loop → `docker compose logs app | tail -50`.
- **First aid**: `docker compose up -d` restarts stopped containers; disk
  full → check `/backups` rotation and purge (entries 7).
- **Reproduce**: `docker compose stop postgres` locally → healthz shows
  `db:false` (that's also the pin — T-OBS-02 covers it).
- **STOP** if crash-looping after one restart: capture logs, full session.
  Incident playbook: runbook §5 (stop app, snapshot logs, rotate secrets).

---

**Escalation rule of thumb**: first-aid buttons (re-run, mark-paid, manual
purge, restart) are yours at 2am. Anything touching `services/rules/`,
`services/pricing/`, or a template is a Claude Code session with the failing
test written FIRST.
