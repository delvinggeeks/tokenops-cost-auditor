# MCP server

Query your TokenOps data from an AI dev tool — Claude Desktop, Cursor, or
anything that speaks [MCP](https://modelcontextprotocol.io) — without leaving
your editor. The server is a thin, **read-only** wrapper over the existing
[read API](reference.md#read-your-data): it mints no new data access, and it
enforces nothing on your LLM traffic (X-01/X-02 stand — this is a read tool,
never a proxy).

## Install

The MCP server ships inside the `tokenops-cost-auditor` package — installing
the [Python SDK](reference.md#python-sdk) already gives you the `mcp`
command:

```bash
pip install tokenops-cost-auditor
```

That gives you two equivalent ways to launch the server over stdio —
`tokenops-cost-auditor mcp` or `python -m tokenops_cost_auditor.mcp` — though
you'll usually let your AI dev tool launch it for you (below).

## Mint a read token

Under **Developer → API tokens**, mint a personal read token and tick both
scopes (`read:audits`, `read:findings`). It's shown once:

```
rt_7Qx…
```

## Configure your AI dev tool

The server authenticates from one environment variable — the same
`TOKENOPS_COST_AUDITOR_TOKEN` the [API reference](reference.md#read-your-data)
already teaches for curl/Python:

=== "Claude Desktop"

    Add this to `claude_desktop_config.json`:

    ```json
    {
      "mcpServers": {
        "tokenops-cost-auditor": {
          "command": "tokenops-cost-auditor",
          "args": ["mcp"],
          "env": {
            "TOKENOPS_COST_AUDITOR_TOKEN": "rt_7Qx…"
          }
        }
      }
    }
    ```

=== "Cursor"

    Add this to `.cursor/mcp.json` (project) or your global MCP settings:

    ```json
    {
      "mcpServers": {
        "tokenops-cost-auditor": {
          "command": "python",
          "args": ["-m", "tokenops_cost_auditor.mcp"],
          "env": {
            "TOKENOPS_COST_AUDITOR_TOKEN": "rt_7Qx…"
          }
        }
      }
    }
    ```

Self-hosted? Point at your own instance with one more variable:

```json
"env": {
  "TOKENOPS_COST_AUDITOR_TOKEN": "rt_7Qx…",
  "TOKENOPS_COST_AUDITOR_SERVER": "https://tokenops.your-company.com"
}
```

Restart the tool — it starts the server over stdio, lists the two tools
below, and is ready to answer questions like *"what are my top three
findings by dollar impact?"* right inside your chat.

## Tools

Both tools call the exact same route as the [read API](reference.md#read-your-data)
— **counts and dollars only**, never a prompt or completion (FR-22). Scopes
are enforced server-side, same as any other read-token call: a token minted
without `read:findings` gets a clean, readable denial from `list_findings`
instead of data.

| Tool | Scope | Calls | Returns |
|---|---|---|---|
| `list_audits` | `read:audits` | `GET /api/v1/audits` | Recent audits — status, spend totals, finding counts |
| `list_findings` | `read:findings` | `GET /api/v1/audits/{audit_id}/findings` | An audit's findings, ranked by monthly dollar impact |

### `list_audits`

Optional input: `limit` (integer, 1–200, default 50).

### `list_findings`

Required input: `audit_id` (string) — from `list_audits`.

## Write tools

None in this release — read-only by design (per PLAN-SDK; write tools are a
future slice). The server can never mint an audit, revoke a token, or touch
your LLM traffic.
