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

    def test_ops_added_for_workflows(self) -> None:
        gates = gr.select_gates([".github/workflows/gate-round.yml"])
        assert "ops-engineer" in gates

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
