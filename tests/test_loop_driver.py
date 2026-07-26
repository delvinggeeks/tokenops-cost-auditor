"""LE-5 — autonomous issue driver (docs/09-SDLC §6). select_ready + build_prompt are
pure, so the orchestration and — critically — the CI laws baked into the agent's
instruction are pinned without spending a run. The live agent path invokes the CLI."""

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


ld = load_script("loop_driver")


def _issue(n: int, *labels: str) -> dict:
    return {"number": n, "title": f"t{n}", "body": "", "labels": [{"name": x} for x in labels]}


class TestSelectReady:
    def test_only_ready_not_already_in_progress(self) -> None:
        issues = [
            _issue(5, "loop:ready"),
            _issue(3, "loop:ready", "loop:in-progress"),  # already claimed — skip
            _issue(9, "bug"),  # not ready
        ]
        got = ld.select_ready(issues, limit=5)
        assert [i["number"] for i in got] == [5]

    def test_fifo_lowest_number_first(self) -> None:
        issues = [_issue(12, "loop:ready"), _issue(4, "loop:ready"), _issue(7, "loop:ready")]
        assert [i["number"] for i in ld.select_ready(issues, limit=2)] == [4, 7]

    def test_none_ready_is_empty(self) -> None:
        assert ld.select_ready([_issue(1, "bug")]) == []


class TestBuildPromptEncodesEveryLaw:
    def _p(self) -> str:
        return ld.build_prompt(42, "Add a widget", "AC: 1. it renders", "dev@example.com")

    def test_carries_the_issue(self) -> None:
        p = self._p()
        assert "#42" in p and "Add a widget" in p and "AC: 1. it renders" in p

    def test_authorship_law_no_ai_trailer(self) -> None:
        p = self._p()
        assert ld.AUTHOR_NAME in p
        assert "NO co-author trailer" in p and "NO AI reference" in p

    def test_scope_freeze_and_engine_boundary(self) -> None:
        p = self._p()
        assert "X-01..X-05" in p and "FR-22" in p and "T-NFR-01" in p

    def test_vertical_slice_and_pinned_toolchain(self) -> None:
        p = self._p()
        assert "VERTICAL SLICE" in p
        assert "uv run ruff" in p and "uv run mypy" in p and "uv run pytest" in p

    def test_hands_it_to_the_loop_not_self_merge(self) -> None:
        p = self._p()
        assert "Closes #42" in p  # merging closes the issue
        assert "auto-merge" in p  # hand to LE-3
        assert "do NOT merge it yourself" in p and "never use --admin" in p

    def test_warns_headless_single_pass_never_background_wait(self) -> None:
        # The first live run failed here: the agent backgrounded its tests and yielded
        # to "wait", but headless runs don't resume — the commit/PR never happened.
        p = self._p()
        assert "HEADLESS" in p
        assert "ONE synchronous pass" in p
        assert "NEVER background" in p

    def test_dry_run_returns_the_prompt_without_a_run(self) -> None:
        out = ld.run_agent(1, "t", "b", "e@x.com", dry_run=True)
        assert "autonomous build agent" in out


class TestWorkflowValidity:
    def test_no_workflow_uses_secrets_in_an_if(self) -> None:
        # GitHub FORBIDS the `secrets` context in an `if:` — it silently invalidates the
        # ENTIRE workflow (0s startup failure). This bit loop-driver.yml on the first run;
        # guard every workflow so it can't recur.
        import yaml

        for wf_path in Path(".github/workflows").glob("*.yml"):
            wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
            for job in wf.get("jobs", {}).values():
                assert "secrets." not in str(job.get("if", "")), wf_path.name
                for step in job.get("steps", []):
                    assert "secrets." not in str(step.get("if", "")), wf_path.name
