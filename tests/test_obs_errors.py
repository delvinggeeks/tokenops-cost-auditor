"""WP-DEVOPS-OBS tests — the error-tracking hook's FR-22 scrubber and
release wiring. The SDK itself is optional; these tests never require it."""

from __future__ import annotations

from tokenops_cost_auditor.obs.errors import _scrub


class TestScrubber:
    def test_01_request_payloads_and_identifiers_stripped(self) -> None:
        event = {
            "request": {
                "url": "https://tokenops-cost-auditor.com/upload",
                "method": "POST",
                "data": {"file": "raw customer log bytes"},
                "headers": {"Authorization": "Bearer secret"},
                "cookies": "session=abc",
                "query_string": "email=someone@example.com",
                "env": {"REMOTE_ADDR": "1.2.3.4"},
            },
            "breadcrumbs": {"values": [{"message": "user someone@example.com signed in"}]},
            "user": {"email": "someone@example.com"},
            "exception": {"values": [{"type": "ValueError"}]},
        }
        out = _scrub(event, {})
        req = out["request"]
        for gone in ("data", "headers", "cookies", "query_string", "env"):
            assert gone not in req
        assert req["url"]  # route context stays — it names no customer
        assert "breadcrumbs" not in out and "user" not in out
        assert out["exception"]["values"][0]["type"] == "ValueError"  # stack survives

    def test_02_scrub_tolerates_minimal_events(self) -> None:
        assert _scrub({}, {}) == {}
        assert _scrub({"request": None}, {}) == {"request": None}


class TestFrameLocalsAndReInit:
    def test_03_sensitive_frame_locals_and_extra_stripped(self) -> None:
        """cold-review f.1/f.3: an exception raised with customer content in
        a local variable must never ship it — vars, extra and contexts are
        stripped; the stack structure itself survives."""
        event = {
            "exception": {
                "values": [
                    {
                        "type": "ValueError",
                        "value": "bad row",
                        "stacktrace": {
                            "frames": [
                                {
                                    "function": "parse_page",
                                    "vars": {"raw": "sk-secret prompt text"},
                                },
                                {"function": "run_pull", "vars": {"key": "sk-live"}},
                            ]
                        },
                    }
                ]
            },
            "extra": {"payload": "customer content"},
            "contexts": {"runtime": {"name": "cpython"}},
        }
        out = _scrub(event, {})
        frames = out["exception"]["values"][0]["stacktrace"]["frames"]
        assert all("vars" not in f for f in frames)
        assert frames[0]["function"] == "parse_page"  # the stack survives
        assert "extra" not in out and "contexts" not in out
        assert "sk-secret" not in str(out) and "sk-live" not in str(out)

    def test_04_reinit_without_dsn_disarms(self, monkeypatch) -> None:
        """cold-review f.2: a re-init WITHOUT a DSN must reset the armed
        flag — zero egress cannot depend on process history."""
        from tokenops_cost_auditor.obs import errors

        monkeypatch.setattr(errors, "_sentry_enabled", True)
        errors.init_errors("", "prod")
        assert errors._sentry_enabled is False

    def test_05_app_boots_with_and_without_dsn(self, tmp_path) -> None:
        """system-tester Q1 closed empirically: the app boots and serves
        healthz with SENTRY_DSN unset AND with a syntactically-valid dummy
        DSN (init performs no network I/O)."""
        try:
            self._boot_both(tmp_path)
        finally:
            # disarm the GLOBAL sdk the armed scenario initialized — without
            # this the test session itself attempts egress at exit (the exact
            # leak the zero-egress law forbids), and later tests' error logs
            # would be captured as pending events
            import sentry_sdk

            from tokenops_cost_auditor.obs import errors

            sentry_sdk.init(dsn="")
            errors._sentry_enabled = False

    def _boot_both(self, tmp_path) -> None:
        from fastapi.testclient import TestClient

        from tokenops_cost_auditor.config import Settings
        from tokenops_cost_auditor.main import create_app
        from tokenops_cost_auditor.persistence.models import Base

        for i, dsn in enumerate(("", "https://k@o0.ingest.sentry.io/0")):
            settings = Settings(
                app_env="test",
                secret_key="test-secret",
                sentry_dsn=dsn,
                database_url=f"sqlite:///{tmp_path}/boot{i}.db",
                upload_dir=tmp_path / f"up{i}",
                report_dir=tmp_path / f"rep{i}",
                backup_dir=tmp_path / f"bak{i}",
                _env_file=None,
            )
            app = create_app(settings)
            Base.metadata.create_all(app.state.engine)
            resp = TestClient(app).get("/healthz")
            assert resp.status_code == 200 and resp.json()["ok"] is True
            app.state.engine.dispose()
