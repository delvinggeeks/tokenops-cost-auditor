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


class TestLoopCloseIssuesWorkflow:
    """LE-5 robustness: GitHub's native `Closes #N` auto-close proved UNRELIABLE for
    app-merged PRs (#37/#38 both stayed open despite a parsed closing reference), so a
    post-merge workflow closes the linked issue deterministically — from GitHub's OWN
    `closingIssuesReferences`, never a body regex, so it can only close what GitHub
    itself linked as closing."""

    WF = Path(".github/workflows/loop-close-issues.yml")

    def _yaml(self) -> dict:
        import yaml

        return yaml.safe_load(self.WF.read_text(encoding="utf-8"))

    def test_exists_and_parses(self) -> None:
        assert self.WF.exists()
        assert self._yaml()  # valid YAML → not a 0s-invalid workflow

    def test_triggers_on_pr_closed(self) -> None:
        # PyYAML parses the `on:` key as the boolean True — accept either spelling.
        wf = self._yaml()
        triggers = wf.get(True, wf.get("on", {}))
        assert "closed" in triggers["pull_request"]["types"]

    def test_only_acts_on_a_real_merge(self) -> None:
        job = self._yaml()["jobs"]["close-linked"]
        assert "github.event.pull_request.merged == true" in str(job["if"])

    def test_closes_from_githubs_own_parse_not_a_regex(self) -> None:
        # The safety property: only issues GitHub linked as closing are ever closed.
        text = self.WF.read_text(encoding="utf-8")
        assert "closingIssuesReferences" in text
        assert "gh issue close" in text

    def test_clears_the_loop_labels(self) -> None:
        text = self.WF.read_text(encoding="utf-8")
        assert "--remove-label loop:in-progress" in text
        assert "--remove-label loop:ready" in text

    def test_has_issues_write_permission(self) -> None:
        assert self._yaml()["permissions"]["issues"] == "write"

    def test_declares_pull_requests_read(self) -> None:
        # `closingIssuesReferences` is a Pull Requests resource; an explicit permissions
        # block sets every unlisted scope to `none`, so without this the GraphQL call
        # 403s and the step aborts on EVERY merge (gate-round caught this on PR #43).
        assert self._yaml()["permissions"]["pull-requests"] == "read"

    def test_no_silent_truncation_of_linked_issues(self) -> None:
        # If a PR ever links more issues than the fetch window, say so loudly.
        text = self.WF.read_text(encoding="utf-8")
        assert "totalCount" in text and "WARNING" in text

    def test_job_is_time_bounded(self) -> None:
        assert self._yaml()["jobs"]["close-linked"]["timeout-minutes"] == 5
