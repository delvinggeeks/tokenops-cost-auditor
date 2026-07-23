# Quickstart

Three ways in. Instrument your code with the SDK (one call, then automatic);
connect your provider account (about two minutes, the platform does the
rest); or upload a log file for a one-off.

## Instrument your code: the SDK

For a per-call view — fuller than the provider connectors give, because it
sees every request — drop the SDK into your app.

1. **Sources → SDK & API → Mint an ingest key.** Copy the DSN it shows once:
   `TOKENOPS_COST_AUDITOR_DSN=https://ik_…@tokenops-cost-auditor.com`. Put it
   in your environment.
2. **One call, then it's automatic:**

   ```python
   import tokenops_cost_auditor.sdk as toca
   toca.init()   # reads TOKENOPS_COST_AUDITOR_DSN from the environment
   ```

   Every OpenAI and Anthropic call your process makes is now counted and
   sent to your account, where it runs through the full six-detector audit.

**What it reads, and what it never touches.** The SDK reads token counts,
the model name, and timing off each response — nothing else. Your prompts
and completions are never read, never serialized, never sent (proven in the
SDK's own test suite). It is observe-only: it never sits in your request
path and never alters, slows, or breaks a call. No DSN set = the SDK is
inert. <!-- src: R-SDK-PLATFORM S-1; FR-22; X-01 -->

## Or connect your provider account — about two minutes

1. [Start free](https://tokenops-cost-auditor.com/signup) — email or Google/Microsoft/
   GitHub sign-in; your first audit is on us, no card.
2. **Sources → Connect** — pick OpenAI or Anthropic and paste a READ-ONLY
   admin/usage key (we show you exactly where to create one). The key is
   encrypted at rest; revoking it deletes the ciphertext.
3. That's it. The platform pulls your usage daily, runs your first audit
   right away, audits weekly on paid plans, emails a daily spend digest,
   and watches between audits with the alerts you arm. We only ever read
   token counts and metadata — the usage APIs don't even contain your
   prompts. <!-- src: R-CONNECT; R-FREE-CONNECT; R-DAILY-LOOP -->

## Option: upload a log file

No connection required — export your logs and upload them for a one-off
audit of that file. The auditor accepts three formats; pick the tab that
matches your stack. <!-- src: FR-01; services/ingest/base.py format detection -->

=== "Claude Code sessions"

    If your spend is Claude Code agents, the bundled exporter converts local
    session transcripts into an ingestible file — token counts and metadata
    only; no prompt or completion text ever leaves your machine.
    <!-- src: FR-24; scripts/exporters/claude_code_export.py -->

    ```bash
    python claude_code_export.py            # scans ~/.claude/projects
    # or explicitly:
    python claude_code_export.py --source ~/.claude/projects \
        --out tokenops_claude_code_export.jsonl
    ```

    The script is stdlib-only and safe to run anywhere. Each output line
    carries model, timestamp, the four usage token counts, and the session id
    as a `tag` — which lets the report break waste down per agent session.

    One framing note, stated on the report itself: Claude Code runs on a
    subscription plan, not metered API billing, so for these audits "Figures
    are API-equivalent token value; actual billing depends on your plan."
    The waste patterns are real either way — the dollar figures tell you what
    the same traffic would cost at API rates.
    <!-- src: FR-30 R-EQUIV-SPEND verbatim -->

=== "OpenAI / Anthropic JSONL"

    Export per-request usage records as JSONL, one JSON object per line, with
    the standard `usage` block (`prompt_tokens` / `input_tokens`,
    `completion_tokens` / `output_tokens`, cached-token fields where your
    account emits them), `model`, and a timestamp. The parser detects the
    provider per file. <!-- src: services/ingest/{openai_jsonl,anthropic_jsonl}.py -->

    If your logging shipper strips prompt text (good), add a top-level
    `prefix_hash` per line — SHA-256 hex over the first 4,096 prompt
    characters, computed on your side — and the cache, retry, and agent-loop
    detectors run at full hash-verified power without your text ever leaving
    your machine. Wrapper fields `tag`, `request_id`, and
    `request.max_tokens` are honored too and improve per-route findings.
    <!-- src: normalizer prefix_hash passthrough; D11-12 export hardening -->

=== "Generic CSV"

    Any provider, one row per API call. Required header columns
    (case-insensitive): <!-- src: services/ingest/generic_csv.py contract -->

    | Column | Meaning |
    |---|---|
    | `ts` | ISO-8601 (UTC assumed if naive) or unix epoch seconds |
    | `provider` | `openai`, `anthropic`, or any lowercase label |
    | `model` | model id as billed |
    | `prompt_tokens` | TOTAL input tokens, including any cached portion |
    | `completion_tokens` | output tokens |

    Optional: `cached_tokens`, `cache_write_tokens`, `latency_ms`, `endpoint`,
    `request_id`, `tag`, `declared_max_tokens`, `prefix_hash` (SHA-256 hex over
    the first 4096 prompt characters, computed client-side — enables the cache
    and duplicate detectors without your text ever leaving your machine).

    Text columns are not part of the contract and are silently dropped.

## 2. Upload

Sign in with a magic link (email only — no password to create), then upload
your export on the upload page. Files up to 200 MB are accepted; your audit
starts immediately after payment and runs in the background while the status
page tracks queue position and progress.
<!-- src: FR-17 magic link; FR-01 200MB; NFR-13 queue position -->

You can also run the exact same engine locally before you buy — the CLI is the
same code path the service runs: <!-- src: FR-04; cli.py -->

```bash
tokenops-cost-auditor audit your_export.jsonl --out report.pdf --json report.json
```

## 3. Read the report

You get an email when the report is ready. The link is signed and private, and
expires after 30 days; the PDF is attached to the same page for download.
Start with the savings waterfall — findings are ranked by estimated monthly
dollar impact, so the top row is your biggest lever. Field-by-field guidance:
[Reading a report](report/reading-a-report.md).
<!-- src: FR-15 signed URLs; FR-13/14 report content -->

## Troubleshooting an export

- **"could not detect the format"** — the first lines must parse as JSON with
  a `usage` block (JSONL) or as the CSV header row. Aggregate exports (daily
  totals, no per-call rows) are not per-request logs; ask us about
  aggregate-mode audits instead of reshaping them.
- **Rows rejected as invalid** — the report's data-quality section and the
  `row_errors.csv` download list each rejected line and why (missing token
  counts, negative values, unparseable timestamp). Below 95% valid rows the
  audit aborts rather than report on a partial picture.
  <!-- src: FR-03 95% rule -->
- **Timestamps without timezones** are treated as UTC. If your logger writes
  local time, convert before exporting — day-boundary charts and cache-window
  math depend on it. <!-- src: NFR-11 -->
- **File too big?** Split by time range (per week works well) and buy one
  audit per slice, or gzip is fine to store but upload the decompressed file.
- **Detectors showing `estimated` instead of `verified`?** Your export has no
  `prefix_hash` column/field. Add it (see the format tabs above) to upgrade
  cache and loop findings to hash-verified confidence.

!!! warning "MEASUREMENT-PENDING (MP-1)"
    We will publish a measured "export to report in N minutes" end-to-end
    timing here once it is taken from a clean run against the production
    deployment. The steps above are real and test-covered today; only the
    timing claim waits for a measured run.
