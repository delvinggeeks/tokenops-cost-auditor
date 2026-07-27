"""stdio MCP server — the S-3 read surface (PLAN-SDK, R-PLATFORM 2).

Launch: ``tokenops-cost-auditor mcp`` or ``python -m tokenops_cost_auditor.mcp``.
Auth: a read token (``rt_…``, minted under Developer -> API tokens) supplied via
the ``TOKENOPS_COST_AUDITOR_TOKEN`` environment variable — the SAME env var the
API docs already teach for curl/Python. This process never touches a database
or the audit engine: every tool call is a plain HTTP GET against the deployed
instance's existing read API (``web/routes_api_read``), so tenancy and scope
enforcement (``web/api_auth``) happen exactly once, server-side, and are never
duplicated here. Read-only, X-01/X-02 safe — never in a request path, never
enforces anything.

FR-22: the two tools return counts/metadata/dollars only, because that is all
the read API itself ever returns — there is no prompt/completion text to leak.

Wire format: JSON-RPC 2.0, one message per line (the MCP stdio transport).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from typing import Any, TextIO

TOKEN_ENV = "TOKENOPS_COST_AUDITOR_TOKEN"
SERVER_ENV = "TOKENOPS_COST_AUDITOR_SERVER"
DEFAULT_SERVER = "https://tokenops-cost-auditor.com"
PROTOCOL_VERSION = "2024-11-05"

try:
    _VERSION = version("tokenops-cost-auditor")
except PackageNotFoundError:  # editable/dev checkout without a build
    _VERSION = "0.0.0"

_NO_TOKEN = (
    f"no read token configured — set {TOKEN_ENV} to a read token "
    "(mint one under Developer -> API tokens)"
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_audits",
        "description": (
            "List the caller's recent audits — status, spend totals, and finding "
            "counts. Counts and dollars only; never prompt/completion text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "description": "max audits to return (default 50)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "list_findings",
        "description": (
            "List the findings inside one audit, ranked by monthly dollar impact. "
            "Counts and dollars only; never prompt/completion text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "audit_id": {
                    "type": "string",
                    "description": "the audit id, as returned by list_audits",
                }
            },
            "required": ["audit_id"],
        },
    },
]


def _error_message(status: int, payload: Any) -> str:
    """Extract a human sentence from an API response, incl. the NFR-14 envelope."""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and "message" in err:
            return str(err["message"])
        if "detail" in payload:
            return str(payload["detail"])
    return f"request failed ({status}): {payload}"


def _api_get(server: str, token: str, path: str) -> tuple[int, Any]:
    """GET against the deployed read API. Never raises — returns (status, body)."""
    req = urllib.request.Request(
        f"{server.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"detail": body[:300]}
    except urllib.error.URLError as exc:
        return 0, {"detail": str(exc.reason)}


def _text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call_tool(name: Any, arguments: dict[str, Any], *, server: str, token: str | None) -> Any:
    """Run one MCP tool call. Returns either an MCP tool result dict, or a
    sentinel string ``"__unknown_tool__"`` the caller turns into a protocol
    error (an unknown tool name is a client bug, not a data-layer failure)."""
    if name not in {"list_audits", "list_findings"}:
        return "__unknown_tool__"
    if not token:
        return _text_result(_NO_TOKEN, is_error=True)

    if name == "list_audits":
        limit = arguments.get("limit")
        path = "/api/v1/audits"
        if limit is not None:
            path += f"?limit={urllib.parse.quote(str(int(limit)))}"
    else:
        audit_id = arguments.get("audit_id")
        if not audit_id:
            return _text_result("audit_id is required", is_error=True)
        path = f"/api/v1/audits/{urllib.parse.quote(str(audit_id), safe='')}/findings"

    status, payload = _api_get(server, token, path)
    if status == 0:
        return _text_result(
            f"could not reach {server}: {_error_message(status, payload)}", is_error=True
        )
    if not (200 <= status < 300):
        return _text_result(_error_message(status, payload), is_error=True)
    return _text_result(json.dumps(payload))


def handle_request(msg: dict[str, Any], *, server: str, token: str | None) -> dict[str, Any] | None:
    """One JSON-RPC message in, a response dict out — or None for a notification
    (a message with no ``id``, which per JSON-RPC 2.0 gets no reply)."""
    msg_id = msg.get("id")
    method = msg.get("method")
    is_notification = "id" not in msg

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "tokenops-cost-auditor", "version": _VERSION},
        }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if is_notification:
        return None  # unknown notification — silently ignored per spec

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        result = call_tool(name, arguments, server=server, token=token)
        if result == "__unknown_tool__":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def run_stdio(
    *,
    server: str,
    token: str | None,
    in_stream: TextIO | None = None,
    out_stream: TextIO | None = None,
) -> None:
    """The stdio read loop: one JSON-RPC message per line in, one out."""
    in_stream = in_stream if in_stream is not None else sys.stdin
    out_stream = out_stream if out_stream is not None else sys.stdout
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            reply = handle_request(msg, server=server, token=token)
        if reply is not None:
            out_stream.write(json.dumps(reply) + "\n")
            out_stream.flush()


def main() -> int:
    server = os.environ.get(SERVER_ENV, DEFAULT_SERVER)
    token = os.environ.get(TOKEN_ENV)
    run_stdio(server=server, token=token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
