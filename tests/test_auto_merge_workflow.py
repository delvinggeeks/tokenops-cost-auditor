"""LE-3 — auto-merge workflow config integrity (docs/09-SDLC §6). A workflow can't be
exercised in a unit test, so pin the invariants that keep it SAFE: opt-in per PR by
label, non-draft only, GitHub NATIVE auto-merge (so branch protection is the real gate,
not this workflow), and least-privilege permissions."""

from pathlib import Path

import yaml

WF = Path(".github/workflows/auto-merge.yml")


def _wf() -> dict:
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _on(wf: dict) -> dict:
    # PyYAML parses a workflow's `on:` key as the boolean True (YAML 1.1 quirk).
    return wf.get("on", wf.get(True))


class TestAutoMergeWorkflowIsSafe:
    def test_it_is_opt_in_per_pr_and_never_on_drafts(self) -> None:
        guard = _wf()["jobs"]["arm-auto-merge"]["if"]
        assert "auto-merge" in guard  # the label arms it
        assert "draft == false" in guard  # never a draft

    def test_it_uses_native_auto_merge_so_branch_protection_is_the_gate(self) -> None:
        run = _wf()["jobs"]["arm-auto-merge"]["steps"][0]["run"]
        assert "gh pr merge" in run and "--auto" in run  # queue, don't force
        assert "--squash" in run

    def test_it_triggers_when_a_label_is_added(self) -> None:
        assert "labeled" in _on(_wf())["pull_request"]["types"]

    def test_permissions_are_least_privilege(self) -> None:
        assert _wf()["permissions"] == {"contents": "write", "pull-requests": "write"}
