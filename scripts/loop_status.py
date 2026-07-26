#!/usr/bin/env python
"""LE-6 — loop status + kill-switch surface (docs/09-SDLC §6). One command answers
"is the loop armed, paused, or wedged?": the LOOP_PAUSED kill-switch, auto-merge (LE-3)
enabled, gate-round (LE-4) enforced, which PRs are armed to auto-merge, and the recent
gate-round pass rate.

The kill-switch itself lives in the workflows — a paused loop (LOOP_PAUSED='true') arms
nothing, honored everywhere. This is the OBSERVABILITY half. `render_status()` is pure so
the formatting is unit-tested; live mode reads the real state via the `gh` CLI.

  Pause:  gh variable set LOOP_PAUSED --body true      (halts ALL auto-merge instantly)
  Resume: gh variable set LOOP_PAUSED --body false
  Status: uv run python scripts/loop_status.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

REPO = "delvinggeeks/tokenops-cost-auditor"
MACHINE_GATE = "gate-round"  # the check LE-4 adds to branch protection


def render_status(state: dict[str, object]) -> str:
    """Pure: a state dict → a readable one-screen report. No network."""
    paused = bool(state.get("paused"))
    armed_raw = state.get("armed_prs")
    armed = armed_raw if isinstance(armed_raw, list) else []
    recent_raw = state.get("gate_round_recent")
    recent = recent_raw if isinstance(recent_raw, list) else []
    lines = ["# Loop status", ""]
    lines.append(
        "- Kill-switch (LOOP_PAUSED): "
        + ("⛔ PAUSED — nothing auto-merges" if paused else "▶ running")
    )
    lines.append(
        "- Auto-merge (LE-3): "
        + ("✅ enabled" if state.get("auto_merge_enabled") else "❌ disabled")
    )
    lines.append(
        "- Gate round (LE-4): "
        + (
            "✅ REQUIRED — a FAIL blocks merge"
            if state.get("gate_round_required")
            else "⚠️ advisory only"
        )
    )
    armed_note = (" — " + ", ".join(f"#{n}" for n in armed)) if armed else ""
    lines.append(f"- PRs armed to auto-merge: {len(armed)}{armed_note}")
    if recent:
        passed = sum(1 for r in recent if r == "success")
        lines.append(f"- Gate round (last {len(recent)} runs): {passed}/{len(recent)} passed")
    return "\n".join(lines)


def _gh_json(args: list[str]) -> Any:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    txt = out.stdout.strip()
    return json.loads(txt) if txt else None


def gather_state() -> dict[str, object]:
    repo = _gh_json(["api", f"repos/{REPO}"]) or {}
    checks = (
        _gh_json(["api", f"repos/{REPO}/branches/main/protection/required_status_checks"]) or {}
    )
    paused_var = _gh_json(["api", f"repos/{REPO}/actions/variables/LOOP_PAUSED"]) or {}
    prs = _gh_json(["pr", "list", "--repo", REPO, "--json", "number,autoMergeRequest"]) or []
    runs = (
        _gh_json(
            [
                "run",
                "list",
                "--repo",
                REPO,
                "--workflow=gate-round.yml",
                "-L",
                "10",
                "--json",
                "conclusion",
            ]
        )
        or []
    )
    return {
        "auto_merge_enabled": bool(repo.get("allow_auto_merge")),
        "gate_round_required": MACHINE_GATE in (checks.get("contexts") or []),
        "paused": (paused_var.get("value") == "true"),
        "armed_prs": [p["number"] for p in prs if p.get("autoMergeRequest")],
        "gate_round_recent": [r["conclusion"] for r in runs if r.get("conclusion")],
    }


def main() -> int:
    print(render_status(gather_state()))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
