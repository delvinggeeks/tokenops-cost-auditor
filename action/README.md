# TokenOps Cost Auditor — GitHub Action

Post your latest LLM-spend audit findings to the GitHub **job summary**, and optionally fail
the job on high-severity waste. Read-only (a `rt_…` read token), observe-only — nothing enters
your request path, no prompt/completion text is ever sent.

## Usage

```yaml
- uses: delvinggeeks/tokenops-cost-auditor/action@main
  with:
    read-token: ${{ secrets.TOKENOPS_READ_TOKEN }}   # rt_… with read:audits + read:findings
    fail-on-severity: high                            # optional: low | medium | high (empty = never fail)
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `read-token` | yes | — | A read token (`rt_…`) with `read:audits` + `read:findings`. |
| `base-url` | no | hosted instance | API origin. |
| `fail-on-severity` | no | `""` | Fail the job if a finding at/above this severity exists. |

It fetches your latest **completed** audit, writes a table of findings ranked by monthly
dollar impact to `$GITHUB_STEP_SUMMARY`, and — if `fail-on-severity` is set — exits non-zero
when a finding meets the threshold.

## Development

```bash
npm ci
npm run typecheck   # strict tsc
npm test            # node --test
npm run build       # tsc → dist/main.js  (commit dist — the Action runs it directly)
```
