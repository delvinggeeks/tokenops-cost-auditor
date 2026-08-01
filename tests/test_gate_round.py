"""LE-4 — gate-round harness tests (docs/09-SDLC §6). Exercises the harness's own
logic — verdict parsing, gate selection, aggregation, exit code, PR comment — WITHOUT
any API call. The live agent path (`_run_agent_live`) is out of scope here: it needs
ANTHROPIC_API_KEY and one validation run on a throwaway PR before the check is required.
"""

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


gr = load_script("gate_round")


class TestParseVerdict:
    def test_plain_pass(self) -> None:
        assert gr.parse_verdict("... VERDICT: PASS") == "PASS"

    def test_fail(self) -> None:
        assert gr.parse_verdict("blah\nVERDICT: FAIL\n1. foo") == "FAIL"

    def test_pass_with_notes_not_shadowed_by_bare_pass(self) -> None:
        # The longest-label-first alternation must win: a bare-PASS match here
        # would silently upgrade a noted verdict to a clean PASS.
        assert gr.parse_verdict("VERDICT: PASS-WITH-NOTES") == "PASS-WITH-NOTES"

    def test_parenthesised_te8_form(self) -> None:
        assert gr.parse_verdict("VERDICT (FAIL) — 1. x:2 bad") == "FAIL"

    def test_bolded_markdown_form(self) -> None:
        assert gr.parse_verdict("**VERDICT:** PASS-WITH-NOTES") == "PASS-WITH-NOTES"

    def test_case_insensitive(self) -> None:
        assert gr.parse_verdict("verdict: fail") == "FAIL"

    def test_no_verdict_is_its_own_state(self) -> None:
        # A gate that produced no verdict did not conclude — it must not pass.
        assert gr.parse_verdict("I ran out of budget, PARTIAL.") == "NO-VERDICT"
        assert gr.parse_verdict("") == "NO-VERDICT"

    def test_last_match_wins_over_echoed_instruction(self) -> None:
        # The killer case: the agent restates the instruction (an early PASS) and then
        # concludes FAIL. First-match would report a false PASS; last-match is correct.
        text = (
            "I will end with VERDICT: PASS | PASS-WITH-NOTES | FAIL as instructed.\n"
            "1. runner.py:247 real bug\n"
            "VERDICT: FAIL\n"
        )
        assert gr.parse_verdict(text) == "FAIL"

    def test_harness_error_tail_is_no_verdict(self) -> None:
        assert gr.parse_verdict("[harness] claude CLI not on PATH — NO-VERDICT.") == "NO-VERDICT"

    def test_label_must_be_whole_word_not_substring(self) -> None:
        # "PASSED"/"FAILING" are not the TE-8 verdict — a missing \b would misread them.
        assert gr.parse_verdict("VERDICT: PASSED all checks") == "NO-VERDICT"
        assert gr.parse_verdict("VERDICT: FAILING intermittently") == "NO-VERDICT"


class TestLiveInvocationIsCrashSafe:
    def test_any_subprocess_error_degrades_to_no_verdict(self, monkeypatch) -> None:
        # One gate's PermissionError/decode error must NOT crash the whole round.
        def boom(*a, **k):
            raise PermissionError("exec denied")

        monkeypatch.setattr(gr.subprocess, "run", boom)
        out = gr._run_agent_live("cold-reviewer", "some diff", "main")
        assert gr.parse_verdict(out) == "NO-VERDICT"

    def test_timeout_degrades_to_no_verdict(self, monkeypatch) -> None:
        def slow(*a, **k):
            raise gr.subprocess.TimeoutExpired(cmd="claude", timeout=gr.AGENT_TIMEOUT_S)

        monkeypatch.setattr(gr.subprocess, "run", slow)
        out = gr._run_agent_live("vv-engineer", "some diff", "main")
        assert gr.parse_verdict(out) == "NO-VERDICT"

    def test_prompt_tells_agents_not_to_rerun_the_full_suite(self, monkeypatch) -> None:
        # The O-2 timeout fix: agents must diff-scope their test run (CI owns the full
        # suite), or they exhaust the budget and NO-VERDICT. Pin the guidance + budget.
        captured: dict[str, object] = {}

        def capture(cmd, **kw):
            captured["prompt"] = kw.get("input")  # prompt travels on STDIN, not argv
            captured["timeout"] = kw.get("timeout")

            class _P:
                stdout, stderr, returncode = "VERDICT: PASS", "", 0

            return _P()

        monkeypatch.setattr(gr.subprocess, "run", capture)
        gr._run_agent_live("vv-engineer", "some diff", "main")
        prompt = captured["prompt"]
        assert "do NOT re-run the whole suite" in prompt
        assert "changed/added test files" in prompt
        assert captured["timeout"] == gr.AGENT_TIMEOUT_S == 1200

    def test_prompt_travels_on_stdin_never_argv(self, monkeypatch) -> None:
        """T-F4 round outage: a prompt embedding a large diff as an argv element
        blows the kernel's 128 KiB per-argument cap (MAX_ARG_STRLEN) and execve
        dies with E2BIG/OSError before the CLI starts — five NO-VERDICTs, twice.
        The prompt must ride stdin (uncapped); no argv element may scale with
        the diff."""
        captured: dict[str, object] = {}

        def capture(cmd, **kw):
            captured["argv"] = cmd
            captured["input"] = kw.get("input")

            class _P:
                stdout, stderr, returncode = "1. fine\n\nVERDICT: PASS", "", 0

            return _P()

        monkeypatch.setattr(gr.subprocess, "run", capture)
        huge_diff = "x" * (300_000)  # well past MAX_ARG_STRLEN if it ever hit argv
        gr._run_agent_live("cold-reviewer", huge_diff, "main")
        argv = captured["argv"]
        assert all(len(str(a)) < 4096 for a in argv), "an argv element scales with the diff"
        assert captured["input"] is not None and huge_diff[:1000] in captured["input"]


class TestLooksTruncated:
    """A verdict-only reply (no findings) is a truncated agent response, not a verdict."""

    def test_bare_non_clean_verdict_is_truncated(self) -> None:
        # FAIL / PASS-WITH-NOTES without findings are charter-invalid (the responses
        # actually seen on PRs #69/#75), so they are retried.
        assert gr._looks_truncated("VERDICT: FAIL") is True
        assert gr._looks_truncated("  VERDICT: PASS-WITH-NOTES  \n") is True
        assert gr._looks_truncated("") is True

    def test_bare_clean_pass_is_NOT_truncated(self) -> None:
        """A terse `VERDICT: PASS` is a valid review, not a truncation.

        Truncation removes the tail and the verdict line IS the tail, so a present
        verdict token is evidence the reply completed; and the charter requires findings
        only for NON-clean verdicts. Before this fix a tersely-clean reviewer was retried
        and, when clean twice, its PASS became a merge-blocking NO-VERDICT — observed on
        PR #111, where the rerun returned the same PASS with the diff unchanged."""
        assert gr._looks_truncated("VERDICT: PASS") is False
        assert gr._looks_truncated("  VERDICT: PASS  \n") is False

    def test_short_reply_with_no_verdict_token_is_still_truncated(self) -> None:
        # guard the fix: shortness alone must not pass — only a clean PASS may.
        assert gr._looks_truncated("hmm") is True

    def test_substantive_review_is_not_truncated(self) -> None:
        assert gr._looks_truncated("1. bug at foo.py:2 — x\n\nVERDICT: FAIL") is False

    def test_harness_no_verdict_string_is_not_retried(self) -> None:
        # deterministic timeout/crash strings carry no verdict token + are long enough —
        # retrying a crash is pointless, so they must read as substantive here.
        assert gr._looks_truncated("[harness] cold-reviewer ... — NO-VERDICT.") is False


class TestTruncatedVerdictRetries:
    def test_retry_recovers_a_substantive_verdict(self, monkeypatch) -> None:
        calls = {"n": 0}

        def fake_cli(agent: str, prompt: str) -> str:
            calls["n"] += 1
            return "VERDICT: FAIL" if calls["n"] == 1 else "1. real finding foo.py:2\nVERDICT: PASS"

        monkeypatch.setattr(gr, "_invoke_cli", fake_cli)
        out = gr._run_agent_live("cold-reviewer", "diff", "main")
        assert calls["n"] == 2  # retried exactly once
        assert gr.parse_verdict(out) == "PASS"

    def test_persistent_truncation_becomes_no_verdict_not_a_bare_fail(self, monkeypatch) -> None:
        calls = {"n": 0}

        def fake_cli(agent: str, prompt: str) -> str:
            calls["n"] += 1
            return "VERDICT: FAIL"

        monkeypatch.setattr(gr, "_invoke_cli", fake_cli)
        out = gr._run_agent_live("cold-reviewer", "diff", "main")
        assert gr.parse_verdict(out) == "NO-VERDICT"
        # the harness performs the retries itself rather than telling a human to
        assert calls["n"] == gr.ATTEMPTS_ON_TRUNCATION
        assert "EXHAUSTED" in out
        # and it SHOWS what came back — a NO-VERDICT that cannot say why is
        # undiagnosable, which is how one agent went five rounds unexplained — but the
        # verdict token inside the excerpt is REDACTED, because parse_verdict reads the
        # LAST match and an un-redacted excerpt would make this message parse as FAIL
        assert "<verdict-token>" in out

    def test_no_verdict_message_shows_an_empty_reply_as_such(self, monkeypatch) -> None:
        monkeypatch.setattr(gr, "_invoke_cli", lambda a, p: "")
        out = gr._run_agent_live("cold-reviewer", "diff", "main")
        assert gr.parse_verdict(out) == "NO-VERDICT"
        assert "<empty>" in out

    def test_substantive_first_reply_is_not_retried(self, monkeypatch) -> None:
        calls = {"n": 0}

        def fake_cli(agent: str, prompt: str) -> str:
            calls["n"] += 1
            return "1. finding foo.py:9 — x\nVERDICT: PASS-WITH-NOTES"

        monkeypatch.setattr(gr, "_invoke_cli", fake_cli)
        out = gr._run_agent_live("vv-engineer", "diff", "main")
        assert calls["n"] == 1  # no wasted retry
        assert gr.parse_verdict(out) == "PASS-WITH-NOTES"


class TestSelectGates:
    def test_core_only_for_docs_and_scripts(self) -> None:
        gates = gr.select_gates(["docs/09-SDLC.md", "scripts/foo.py", "tests/test_foo.py"])
        assert gates == list(gr.CORE_GATES)

    def test_ux_added_for_templates(self) -> None:
        gates = gr.select_gates(["src/tokenops_cost_auditor/web/templates/app/findings.html"])
        assert "ux-reviewer" in gates

    def test_architect_added_for_services(self) -> None:
        gates = gr.select_gates(["src/tokenops_cost_auditor/services/rules/d10.py"])
        assert "architect" in gates

    def test_architect_added_for_uml_diagrams(self) -> None:
        # docs/uml/ is the architect's own artifact surface: a diagram-only diff
        # must draw the architect gate (T-D2 — the round ran without it).
        gates = gr.select_gates(["docs/uml/components.mmd"])
        assert "architect" in gates

    def test_ops_added_for_workflows(self) -> None:
        gates = gr.select_gates([".github/workflows/gate-round.yml"])
        assert "ops-engineer" in gates

    def test_ops_trigger_does_not_match_incidental_docker_compose_substrings(self) -> None:
        # Bare "docker"/"compose" substrings drew a needless ops gate on unrelated paths.
        gates = gr.select_gates(["docs/dockerized-notes.md", "scripts/decompose.py"])
        assert "ops-engineer" not in gates

    def test_this_le4_diff_selects_core_plus_ops(self) -> None:
        # Self-consistency: this very card touches scripts + a workflow + tests + docs,
        # so it draws the core gates plus ops — and NOT ux/architect.
        changed = [
            "scripts/gate_round.py",
            ".github/workflows/gate-round.yml",
            "tests/test_gate_round.py",
            "docs/09-SDLC.md",
        ]
        gates = gr.select_gates(changed)
        assert gates == [*gr.CORE_GATES, "ops-engineer"]


class TestModelTiering:
    def test_every_gate_charter_pins_sonnet(self) -> None:
        # TE-5: the whole cost profile depends on gates running Sonnet, not Opus.
        for agent in [*gr.CORE_GATES, "ux-reviewer", "architect", "ops-engineer"]:
            assert gr.agent_model(agent) == "sonnet", agent

    def test_missing_field_defaults_to_sonnet_never_escalates(self, monkeypatch) -> None:
        # A renamed/absent field must never silently promote a gate to the Opus tier.
        monkeypatch.setattr(gr, "_charter", lambda a: "---\nname: x\n---\nbody")
        assert gr.agent_model("whatever") == "sonnet"

    def test_reads_declared_model(self, monkeypatch) -> None:
        monkeypatch.setattr(gr, "_charter", lambda a: "---\nmodel: haiku\n---\nbody")
        assert gr.agent_model("whatever") == "haiku"


class TestAggregation:
    def _res(self, **verdicts) -> list:
        return [gr.GateResult(agent=a, verdict=v, output="") for a, v in verdicts.items()]

    def test_fail_blocks(self) -> None:
        assert gr.is_blocking(self._res(**{"cold-reviewer": "FAIL", "spec-guard": "PASS"}))

    def test_no_verdict_blocks(self) -> None:
        assert gr.is_blocking(self._res(**{"cold-reviewer": "NO-VERDICT"}))

    def test_pass_with_notes_does_not_block(self) -> None:
        assert not gr.is_blocking(
            self._res(**{"cold-reviewer": "PASS-WITH-NOTES", "spec-guard": "PASS"})
        )

    def test_all_pass_clears(self) -> None:
        assert not gr.is_blocking(self._res(**{"cold-reviewer": "PASS", "spec-guard": "PASS"}))


class TestComment:
    def test_blocked_comment_names_failing_gates(self) -> None:
        res = [
            gr.GateResult("cold-reviewer", "FAIL", ""),
            gr.GateResult("spec-guard", "PASS", ""),
        ]
        out = gr.to_comment(res)
        assert "BLOCKED" in out and "cold-reviewer" in out

    def test_clear_comment_when_all_pass(self) -> None:
        res = [gr.GateResult("cold-reviewer", "PASS", "")]
        assert "All gates cleared" in gr.to_comment(res)

    def test_notes_are_surfaced_for_pass_with_notes(self) -> None:
        # The whole value of a gate is its findings — PASS-WITH-NOTES must show them.
        res = [gr.GateResult("vv-engineer", "PASS-WITH-NOTES", "1. findings.py:12 missing test")]
        out = gr.to_comment(res)
        assert "<details>" in out and "findings.py:12 missing test" in out

    def test_clean_pass_carries_no_findings_block(self) -> None:
        res = [gr.GateResult("spec-guard", "PASS", "some chatter that should NOT render")]
        out = gr.to_comment(res)
        assert "<details>" not in out and "chatter" not in out

    def test_long_findings_truncated_under_comment_cap(self) -> None:
        res = [gr.GateResult("cold-reviewer", "FAIL", "x" * 20000)]
        out = gr.to_comment(res)
        assert "truncated" in out and len(out) < 12000


class TestRunRoundDryRun:
    def test_dry_run_wires_mock_verdicts_through(self, monkeypatch) -> None:
        # Pin the diff so gate selection is deterministic without touching git state.
        monkeypatch.setattr(gr, "_changed_files", lambda base: ["scripts/gate_round.py"])
        results = gr.run_round(
            "origin/main",
            dry_run=True,
            mock={"cold-reviewer": "VERDICT: FAIL", "spec-guard": "VERDICT: PASS"},
        )
        by = {r.agent: r.verdict for r in results}
        assert by["cold-reviewer"] == "FAIL"
        assert by["spec-guard"] == "PASS"
        # An unmocked gate defaults to PASS (the harness must never hang waiting on a mock).
        assert by["vv-engineer"] == "PASS"
        assert gr.is_blocking(results)

    def test_dry_run_default_all_pass_is_green(self, monkeypatch) -> None:
        monkeypatch.setattr(gr, "_changed_files", lambda base: ["docs/09-SDLC.md"])
        results = gr.run_round("origin/main", dry_run=True)
        assert not gr.is_blocking(results)
        assert [r.agent for r in results] == list(gr.CORE_GATES)


class TestGeneratedFixturesNotInlined:
    """The T-F4 fixture pair (5,400-char repeated-prefix lines) is what first
    pushed the prompt past MAX_ARG_STRLEN — generated fixture bytes are named
    in the diff, never inlined (agents read the checkout, TE-3)."""

    def test_diff_excludes_fixture_globs_and_names_them(self, monkeypatch) -> None:
        calls: list[list[str]] = []

        def capture(cmd, **kw):
            calls.append(cmd)

            class _P:
                stderr, returncode = "", 0
                stdout = (
                    "tests/fixtures/fr37_before.jsonl\ntests/fixtures/fr37_after.jsonl"
                    if "--name-only" in cmd
                    else "diff --git a/x b/x\n"
                )

            return _P()

        monkeypatch.setattr(gr.subprocess, "run", capture)
        text = gr._diff("main")
        content_diff = calls[0]
        assert all(exclude in content_diff for exclude in gr.GENERATED_DIFF_EXCLUDES)
        assert "NOT inlined" in text
        assert "tests/fixtures/fr37_before.jsonl" in text
        # The footer query must use the SAME globs as the content exclusion —
        # naming the whole fixtures dir listed inlined .py sources as "not
        # inlined" (G-T-F4 round-4 c.1: self-contradictory prompt).
        footer_query = calls[1]
        assert "tests/fixtures/" not in footer_query
        for spec in gr.GENERATED_DIFF_EXCLUDES:
            assert spec[2:] in footer_query
