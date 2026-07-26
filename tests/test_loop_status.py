"""LE-6 — loop status/kill-switch surface (docs/09-SDLC §6). render_status is pure, so
the report's key signals — paused, auto-merge, gate-round-required, armed PRs, pass
rate — are pinned without any network."""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ls = load_script("loop_status")


class TestRenderStatus:
    def test_paused_is_loud(self) -> None:
        out = ls.render_status({"paused": True, "auto_merge_enabled": True})
        assert "PAUSED" in out and "nothing auto-merges" in out

    def test_running_shows_every_rung(self) -> None:
        out = ls.render_status(
            {
                "paused": False,
                "auto_merge_enabled": True,
                "gate_round_required": True,
                "armed_prs": [34, 40],
                "gate_round_recent": ["success", "failure", "success"],
            }
        )
        assert "▶ running" in out
        assert "✅ enabled" in out  # LE-3
        assert "REQUIRED" in out  # LE-4 enforced
        assert "#34" in out and "#40" in out  # armed PRs listed
        assert "2/3 passed" in out  # gate-round pass rate

    def test_advisory_gate_is_flagged(self) -> None:
        assert "advisory only" in ls.render_status({"gate_round_required": False})

    def test_disabled_auto_merge_is_flagged(self) -> None:
        assert "❌ disabled" in ls.render_status({"auto_merge_enabled": False})

    def test_empty_state_does_not_crash(self) -> None:
        out = ls.render_status({})
        assert "Loop status" in out and "PRs armed to auto-merge: 0" in out
