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
