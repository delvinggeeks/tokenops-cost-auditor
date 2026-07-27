"""T-MCP-01..05 (PLAN-SDK S-3, docs/05 patterns): the stdio MCP read server.

Auth/tenancy/scope enforcement is NOT re-tested here — it already has full
coverage in test_developer_platform.py against the real read API. These tests
pin the MCP wire contract (tools/list shape, tools/call happy path, and the
scope-denied / missing-token / unknown-tool paths) against a mocked HTTP layer,
matching the urllib-mock pattern already used in test_sdk.py.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

from tokenops_cost_auditor.mcp.server import (
    SERVER_ENV,
    TOKEN_ENV,
    call_tool,
    handle_request,
    run_stdio,
)

SERVER = "https://tokenops-cost-auditor.example"
TOKEN = "rt_test123"


def _fake_urlopen_json(status: int, payload: Any, captured: dict[str, Any] | None = None):
    def fake(req: Any, timeout: float = 0) -> Any:
        if captured is not None:
            captured["url"] = req.full_url
            captured["auth"] = req.headers.get("Authorization")
        body = json.dumps(payload).encode()
        if 200 <= status < 300:
            resp = io.BytesIO(body)
            resp.status = status  # type: ignore[attr-defined]

            class R:
                def __enter__(self) -> Any:
                    return resp

                def __exit__(self, *a: Any) -> None:
                    return None

            return R()
        raise urllib.error.HTTPError(req.full_url, status, "error", None, io.BytesIO(body))  # type: ignore[arg-type]

    return fake


class TestToolsList:
    def test_shape_has_both_read_only_tools(self) -> None:
        resp = handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, server=SERVER, token=TOKEN
        )
        assert resp is not None
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {"list_audits", "list_findings"}
        for tool in tools:
            assert tool["description"]
            assert tool["inputSchema"]["type"] == "object"
        findings_tool = next(t for t in tools if t["name"] == "list_findings")
        assert findings_tool["inputSchema"]["required"] == ["audit_id"]

    def test_initialize_returns_server_info(self) -> None:
        resp = handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            server=SERVER,
            token=TOKEN,
        )
        assert resp is not None
        assert resp["result"]["serverInfo"]["name"] == "tokenops-cost-auditor"
        assert resp["result"]["capabilities"] == {"tools": {}}


class TestToolsCallHappyPath:
    def test_list_audits_returns_api_payload(self, monkeypatch: Any) -> None:
        captured: dict[str, Any] = {}
        payload = {"audits": [{"id": "a1", "status": "done", "total_spend_usd": 42.5}]}
        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_json(200, payload, captured))
        resp = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_audits", "arguments": {"limit": 10}},
            },
            server=SERVER,
            token=TOKEN,
        )
        assert resp is not None
        result = resp["result"]
        assert result["isError"] is False
        assert json.loads(result["content"][0]["text"]) == payload
        assert captured["auth"] == f"Bearer {TOKEN}"
        assert captured["url"] == f"{SERVER}/api/v1/audits?limit=10"

    def test_list_findings_returns_api_payload(self, monkeypatch: Any) -> None:
        payload = {
            "audit_id": "a1",
            "findings": [{"id": "d1-001", "monthly_cost_impact_usd": 31.0}],
        }
        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_json(200, payload))
        result = call_tool("list_findings", {"audit_id": "a1"}, server=SERVER, token=TOKEN)
        assert result["isError"] is False
        assert json.loads(result["content"][0]["text"]) == payload

    def test_list_findings_requires_audit_id(self) -> None:
        result = call_tool("list_findings", {}, server=SERVER, token=TOKEN)
        assert result["isError"] is True
        assert "audit_id" in result["content"][0]["text"]


class TestAuthAndScopeFailuresFailCleanly:
    def test_missing_token_never_hits_the_network(self, monkeypatch: Any) -> None:
        def boom(*a: Any, **k: Any) -> Any:
            raise AssertionError("must not make a network call without a token")

        monkeypatch.setattr(urllib.request, "urlopen", boom)
        result = call_tool("list_audits", {}, server=SERVER, token=None)
        assert result["isError"] is True
        assert TOKEN_ENV in result["content"][0]["text"]

    def test_invalid_token_surfaces_the_server_401(self, monkeypatch: Any) -> None:
        envelope = {"error": {"code": "unauthorized", "message": "unknown or revoked API token"}}
        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_json(401, envelope))
        result = call_tool("list_audits", {}, server=SERVER, token="rt_bad")
        assert result["isError"] is True
        assert "unknown or revoked API token" in result["content"][0]["text"]

    def test_token_without_scope_is_denied(self, monkeypatch: Any) -> None:
        envelope = {
            "error": {"code": "forbidden", "message": "this token lacks the 'read:findings' scope"}
        }
        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_json(403, envelope))
        result = call_tool("list_findings", {"audit_id": "a1"}, server=SERVER, token=TOKEN)
        assert result["isError"] is True
        assert "read:findings" in result["content"][0]["text"]

    def test_foreign_audit_is_a_clean_404(self, monkeypatch: Any) -> None:
        envelope = {"error": {"code": "not_found", "message": "audit not found"}}
        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_json(404, envelope))
        result = call_tool("list_findings", {"audit_id": "not-mine"}, server=SERVER, token=TOKEN)
        assert result["isError"] is True
        assert "audit not found" in result["content"][0]["text"]


class TestProtocolEdges:
    def test_unknown_tool_is_a_jsonrpc_error(self) -> None:
        resp = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "delete_everything", "arguments": {}},
            },
            server=SERVER,
            token=TOKEN,
        )
        assert resp is not None
        assert resp["error"]["code"] == -32602

    def test_unknown_method_is_a_jsonrpc_error(self) -> None:
        resp = handle_request(
            {"jsonrpc": "2.0", "id": 4, "method": "prompts/list"}, server=SERVER, token=TOKEN
        )
        assert resp is not None
        assert resp["error"]["code"] == -32601

    def test_notification_gets_no_reply(self) -> None:
        resp = handle_request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, server=SERVER, token=TOKEN
        )
        assert resp is None


class TestStdioLoop:
    def test_initialize_then_notification_then_tools_list(self, monkeypatch: Any) -> None:
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
        inp = io.StringIO("\n".join(lines) + "\n")
        out = io.StringIO()
        monkeypatch.setenv(SERVER_ENV, SERVER)
        run_stdio(server=SERVER, token=TOKEN, in_stream=inp, out_stream=out)
        replies = [json.loads(line) for line in out.getvalue().splitlines()]
        # Exactly two replies: the notification gets none (K-1 spec compliance).
        assert len(replies) == 2
        assert replies[0]["id"] == 1
        assert replies[1]["id"] == 2
        assert {t["name"] for t in replies[1]["result"]["tools"]} == {
            "list_audits",
            "list_findings",
        }
