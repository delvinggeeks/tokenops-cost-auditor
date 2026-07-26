"""Issue #37 — CONTRIBUTING documents the autonomous loop (docs/09-SDLC §6). Pins the
section's existence and its three load-bearing anchors so the doc can't silently drift
from the loop mechanism it describes: the `loop:ready` label, the `LOOP_PAUSED`
kill-switch, and the `loop_status.py` status command."""

from pathlib import Path

CONTRIBUTING = (Path(__file__).parents[1] / "CONTRIBUTING.md").read_text(encoding="utf-8")


class TestAutonomousLoopSection:
    def test_section_exists(self) -> None:
        assert "## The autonomous loop" in CONTRIBUTING

    def _section(self) -> str:
        start = CONTRIBUTING.index("## The autonomous loop")
        rest = CONTRIBUTING[start + len("## The autonomous loop") :]
        end = rest.find("\n## ")
        return rest if end == -1 else rest[:end]

    def test_names_the_ready_label(self) -> None:
        assert "loop:ready" in self._section()

    def test_names_the_kill_switch(self) -> None:
        assert "LOOP_PAUSED" in self._section()

    def test_names_the_status_command(self) -> None:
        assert "loop_status.py" in self._section()

    def test_documents_founder_gated_production(self) -> None:
        section = self._section()
        assert "founder-gated" in section or "founder gated" in section

    def test_documents_ci_laws_the_gate_enforces(self) -> None:
        section = self._section()
        for anchor in ("authorship", "X-01..X-05", "FR-22", "T-NFR-01"):
            assert anchor in section, f"missing CI-law anchor: {anchor}"
