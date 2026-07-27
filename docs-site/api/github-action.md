# GitHub Action

Post your latest LLM-spend audit findings to the GitHub **job summary** in CI, and optionally
fail the job on high-severity waste. Read-only (a `rt_…` read token), observe-only — nothing
enters your request path and no prompt/completion text is ever sent (FR-22). Source: `action/`.

## Usage

```yaml
- uses: delvinggeeks/tokenops-cost-auditor/action@main
  with:
    read-token: ${{ secrets.TOKENOPS_READ_TOKEN }}   # rt_… with read:audits + read:findings
    fail-on-severity: high                            # optional: low | medium | high
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `read-token` | yes | — | Read token (`rt_…`) with `read:audits` + `read:findings`. |
| `base-url` | no | hosted instance | API origin. |
| `fail-on-severity` | no | `""` | Fail the job if a finding at/above this severity exists. |

It calls `GET /api/v1/audits` (scope `read:audits`) for your latest completed audit and
`GET /api/v1/audits/{id}/findings` (scope `read:findings`), writes a table ranked by monthly
dollar impact to `$GITHUB_STEP_SUMMARY`, and exits non-zero when `fail-on-severity` is met.

See the [reference](reference.md) for the underlying endpoints, or the
[JS/TS SDK](sdk-js.md) to build a custom integration.
