"""MCP server (PLAN-SDK S-3) — query TokenOps from AI dev tools over stdio.

Thin read-only client over the existing read API (web/routes_api_read); it
mints no new data access and enforces no scope itself — tenancy and scope
checks stay server-side, exactly as they do for any other read-token caller.
"""

from __future__ import annotations
