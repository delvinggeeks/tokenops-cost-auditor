"""D1 scaffold smoke tests: T-OBS-01..03 (docs/05-TEST-PLAN.md §3) plus an
.env.example completeness guard (runbook §5 secrets discipline)."""

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.obs import errors as obs_errors


class TestTOBS01RequestIdLogging:
    def test_request_id_present_in_log_lines(self, client: TestClient) -> None:
        with capture_logs() as logs:
            resp = client.get("/healthz")
        access_events = [e for e in logs if e["event"] == "request"]
        assert access_events, "no access log event emitted"
        assert re.fullmatch(r"[0-9a-f]{16}", access_events[0]["request_id"])
        assert access_events[0]["path"] == "/healthz"
        assert resp.headers["X-Request-ID"] == access_events[0]["request_id"]

    def test_inbound_request_id_is_honored(self, client: TestClient) -> None:
        resp = client.get("/healthz", headers={"X-Request-ID": "trace-abc-123"})
        assert resp.headers["X-Request-ID"] == "trace-abc-123"


class TestTOBS02Healthz:
    def test_healthy(self, client: TestClient) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["db"] is True
        assert body["disk_free_mb"] > 0

    def test_degrades_when_db_down(self, settings: Settings) -> None:
        bad = settings.model_copy(
            update={"database_url": "postgresql+psycopg://nobody@127.0.0.1:59999/nodb"}
        )
        bad_app = create_app(bad)
        try:
            client = TestClient(bad_app)
            resp = client.get("/healthz")
            assert resp.status_code == 503
            body = resp.json()
            assert body["ok"] is False
            assert body["db"] is False
        finally:
            bad_app.state.engine.dispose()


class TestTOBS03ErrorHook:
    def test_error_hook_called_on_unhandled_error(self, app: FastAPI, monkeypatch) -> None:
        captured: list[BaseException] = []
        monkeypatch.setattr(obs_errors, "capture_exception", captured.append)

        @app.get("/_boom")
        async def boom() -> None:
            raise ValueError("internal detail that must not leak")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/_boom")
        assert resp.status_code == 500
        assert resp.json() == {"error": "internal error"}  # user-safe (LLD §8)
        assert "internal detail" not in resp.text
        assert len(captured) == 1
        assert isinstance(captured[0], ValueError)


def test_env_example_complete() -> None:
    """Every Settings field must appear in .env.example (ops gate check 3)."""
    example = Path(".env.example").read_text()
    declared = {
        line.split("=", 1)[0].strip()
        for line in example.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = {name.upper() for name in Settings.model_fields} - declared
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_env_example_boots_a_fresh_deploy() -> None:
    """A FRESH deploy loads its config from .env.example, which ships every
    optional key BLANK (e.g. ONE_SHOT_USD=). Settings must treat blank as unset
    and boot on defaults — regression pin for the staging-caught crash-loop
    (2026-07-24): pydantic rejected "" as a float, so a fresh box crash-looped
    while prod survived on its populated .env. Booting here means it won't."""
    s = Settings(_env_file=".env.example")
    # a representative optional pricing float that was blank in .env.example
    assert s.one_shot_usd == 500.0
    assert s.plan_pro_spend_gate_usd == 25000.0
