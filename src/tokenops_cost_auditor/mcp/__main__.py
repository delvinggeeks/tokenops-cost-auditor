"""``python -m tokenops_cost_auditor.mcp`` — the stdio MCP server entry point."""

from __future__ import annotations

from tokenops_cost_auditor.mcp.server import main

if __name__ == "__main__":
    raise SystemExit(main())
