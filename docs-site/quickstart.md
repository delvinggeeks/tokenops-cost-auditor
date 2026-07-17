# Quickstart

Three steps: export your logs, upload them, read the report.

## 1. Export your logs

The auditor accepts three formats. Pick the tab that matches your stack.
<!-- src: FR-01; services/ingest/base.py format detection -->

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

=== "OpenAI / Anthropic JSONL"

    Export per-request usage records as JSONL, one JSON object per line, with
    the standard `usage` block (`prompt_tokens` / `input_tokens`,
    `completion_tokens` / `output_tokens`, cached-token fields where your
    account emits them), `model`, and a timestamp. The parser detects the
    provider per file. <!-- src: services/ingest/{openai_jsonl,anthropic_jsonl}.py -->

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

!!! warning "MEASUREMENT-PENDING (MP-1)"
    We will publish a measured "export to report in N minutes" end-to-end
    timing here once it is taken from a clean run against the production
    deployment. The steps above are real and test-covered today; only the
    timing claim waits for a measured run.
