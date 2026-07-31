"""LE-7 (docs/09-SDLC.md §6, ADR-8, docs/internal/QUEUE.md T-T1) — adoption of
pytest-requirements as the single source of the requirement<->test edge.

This file is CLAUDE.md rule 7 / docs/09 tooling (SDLC/CI tooling, the same
class as gate_round.py and check_authorship.py) — it owns no docs/04 row and
carries no verifies_requirement marker itself (see TestToolingOwnsNoMarker).
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_DOC = ROOT / "docs" / "01-REQUIREMENTS.md"
_REQUIREMENT_LINE_RE = re.compile(r"^(FR|NFR)-(\d+) \(([A-Z])")

# LE-* / CLAUDE.md rule 7 tooling test files: they own no docs/01 requirement,
# so per the R-TRACE convention they must never carry a verifies_requirement
# marker (a docs/04 row is forbidden for them; a marker would contradict that).
TOOLING_TEST_FILES = frozenset(
    {
        "test_gate_round.py",
        "test_loop_driver.py",
        "test_loop_status.py",
        "test_auto_merge_workflow.py",
        "test_pricing_verify.py",
        "test_pricing_sync.py",
        "test_traceability.py",
    }
)

# Requirements with no pytest-collectible automated test, EXEMPT BY
# DECLARATION — never by silence (the LE-8 convention this card establishes
# early, docs/09-SDLC.md §6). Each reason is independently checkable in
# docs/04-TRACEABILITY.md or docs/internal/QUEUE.md.
EXEMPT_FROM_MARKER_COVERAGE: dict[str, str] = {
    "NFR-02": "TLS/secrets posture — docs/04 T-OPS-01 is a manual review, not pytest-collectible",
    "NFR-08": "backup/restore drill — docs/04 T-OPS-02 is a manual, logged drill",
    "NFR-09": "compose/Caddy/runbook deploy — docs/04 T-OPS-03 is a manual review",
    "NFR-04": (
        "T-PERF-01 carries @pytest.mark.perf and is excluded from the default "
        "'-m not perf' run (CLAUDE.md rule / TE-11 pinned toolchain command); "
        "still collected and marked, just not part of this suite's default pass"
    ),
    "FR-34": (
        "Model factory separation core span is design-registered/unbuilt "
        "(docs/04 FR-34 row; QUEUE T-F1) — its shipped sub-spans FR-35..38 "
        "are covered individually below"
    ),
    "FR-39": (
        "deployment modes — design-registered, trigger-gated, zero build "
        "authorized (docs/04 FR-39..42 row)"
    ),
    "FR-40": "Lane-A zero-touch release — design-registered, trigger-gated, zero build authorized",
    "FR-41": "Lane-B zero-touch updates — design-registered, trigger-gated, zero build authorized",
    "FR-42": "scale claims discipline — design-registered, trigger-gated, zero build authorized",
}


def _requirement_priorities() -> dict[str, str]:
    priorities: dict[str, str] = {}
    for line in REQUIREMENTS_DOC.read_text().splitlines():
        m = _REQUIREMENT_LINE_RE.match(line)
        if m:
            priorities[f"{m.group(1)}-{m.group(2)}"] = m.group(3)
    return priorities


@pytest.fixture(scope="session")
def requirement_test_map(request: pytest.FixtureRequest) -> dict[str, set[str]]:
    """The requirement -> test-nodeid map, built from collection alone (no
    test body ever runs to produce it) — the same guarantee the issue's probe
    below demonstrates in isolation."""
    mapping: dict[str, set[str]] = {}
    for item in request.session.items:
        for marker in item.iter_markers(name="verifies_requirement"):
            mapping.setdefault(marker.args[0], set()).add(item.nodeid)
    return mapping


class TestMPriorityCoverage:
    """Measurable check (docs/09-SDLC.md §6): every M-priority FR/NFR resolves
    to >=1 verifies_requirement-marked test, unless declared exempt above."""

    def test_every_m_priority_requirement_is_marked(
        self, requirement_test_map: dict[str, set[str]]
    ) -> None:
        priorities = _requirement_priorities()
        missing = sorted(
            req_id
            for req_id, priority in priorities.items()
            if priority == "M"
            and req_id not in EXEMPT_FROM_MARKER_COVERAGE
            and not requirement_test_map.get(req_id)
        )
        assert not missing, f"M-priority requirements with no marked test: {missing}"

    def test_exemptions_still_name_real_requirements(self) -> None:
        priorities = _requirement_priorities()
        stale = sorted(r for r in EXEMPT_FROM_MARKER_COVERAGE if r not in priorities)
        assert not stale, f"exempt id(s) no longer in docs/01-REQUIREMENTS.md: {stale}"


class TestUnclaimedCountFallsMaterially:
    """R-TRACE sweep baseline (docs/09-SDLC.md §6, 2026-07-31): 136 of 185
    docs/04-claimed test ids traced to nothing collectible, and 148 of 192
    collected test ids were claimed by no document. Before this card,
    verifies_requirement did not exist, so EVERY collected test was unmarked
    — the same defect restated in marker terms. The LE-7 backfill (this
    commit) marks 295+ individual pytest items across the M-priority FR/NFR
    set; the floor below is a comfortable margin under that achieved count,
    catching a future regression without being sensitive to unrelated growth
    in the total test count."""

    def test_marked_test_count_holds_the_backfill_floor(
        self, request: pytest.FixtureRequest
    ) -> None:
        marked = sum(
            1
            for item in request.session.items
            if any(item.iter_markers(name="verifies_requirement"))
        )
        assert marked >= 250, (
            f"only {marked} collected tests carry a verifies_requirement marker "
            "(was 0 before the LE-7 backfill) — regressed below the floor"
        )


class TestToolingOwnsNoMarker:
    """CLAUDE.md rule 7 / docs/09-SDLC.md §6: LE-* SDLC/CI tooling owns no
    docs/04 row, so its tests must carry no verifies_requirement marker — the
    convention this card's own tests are held to as well."""

    def test_le_track_tooling_tests_carry_no_requirement_marker(
        self, request: pytest.FixtureRequest
    ) -> None:
        offenders = sorted(
            item.nodeid
            for item in request.session.items
            if item.path.name in TOOLING_TEST_FILES
            and any(item.iter_markers(name="verifies_requirement"))
        )
        assert not offenders, f"tooling tests must carry no requirement marker: {offenders}"


class TestPytestRequirementsPluginProbe:
    """Probe (docs/09-SDLC.md §6 measurable check): verifies the FOUR claims
    ADR-8 rests on, each in an isolated pytester sandbox so this file's own
    fixtures/markers can never leak into the assertion."""

    def test_marker_self_registers_with_zero_unknown_mark_warning(
        self, pytester: pytest.Pytester
    ) -> None:
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.verifies_requirement("FR-07")
            def test_marked():
                assert True
            """
        )
        result = pytester.runpytest("-W", "error::pytest.PytestUnknownMarkWarning")
        result.assert_outcomes(passed=1)

    def test_marker_emits_requirement_id_property_into_junit_xml(
        self, pytester: pytest.Pytester
    ) -> None:
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.verifies_requirement("FR-07")
            def test_marked():
                assert True

            def test_unmarked():
                assert True
            """
        )
        report_path = pytester.path / "report.xml"
        result = pytester.runpytest(f"--junit-xml={report_path}")
        result.assert_outcomes(passed=2)

        tree = ET.parse(report_path)
        cases = {tc.attrib["name"]: tc for tc in tree.iter("testcase")}
        marked_props = {
            prop.attrib["value"]
            for prop in cases["test_marked"].iter("property")
            if prop.attrib["name"] == "requirement_id"
        }
        assert marked_props == {"FR-07"}
        unmarked_props = [
            prop
            for prop in cases["test_unmarked"].iter("property")
            if prop.attrib["name"] == "requirement_id"
        ]
        assert unmarked_props == []

    def test_dash_m_verifies_requirement_selects_only_marked_tests(
        self, pytester: pytest.Pytester
    ) -> None:
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.verifies_requirement("FR-07")
            def test_marked():
                assert True

            def test_unmarked():
                assert True
            """
        )
        result = pytester.runpytest("-m", "verifies_requirement", "-v")
        result.assert_outcomes(passed=1)
        result.stdout.fnmatch_lines(["*test_marked*"])
        assert "test_unmarked" not in "\n".join(result.outlines)

    def test_collection_modifyitems_hook_builds_the_map_without_running_the_suite(
        self, pytester: pytest.Pytester
    ) -> None:
        """A 5-line pytest_collection_modifyitems hook is all it takes to turn
        collected markers into the full requirement->test map — proven here by
        a --collect-only run whose test bodies (which would raise if executed)
        never fire."""
        pytester.makeconftest(
            """
            REQUIREMENT_MAP = {}

            def pytest_collection_modifyitems(items):
                for item in items:
                    for marker in item.iter_markers(name="verifies_requirement"):
                        REQUIREMENT_MAP.setdefault(marker.args[0], []).append(item.nodeid)
            """
        )
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.verifies_requirement("FR-07")
            def test_a():
                raise AssertionError("must never execute under --collect-only")

            @pytest.mark.verifies_requirement("FR-08")
            def test_b():
                raise AssertionError("must never execute under --collect-only")
            """
        )
        result = pytester.runpytest("--collect-only", "-q")
        result.assert_outcomes()  # nothing ran — zero passed, zero failed
        assert result.ret == 0
        result.stdout.fnmatch_lines(["*test_a*", "*test_b*"])


class TestUnknownRequirementIdFailsCollection:
    """Guard test (docs/09-SDLC.md §6 measurable check): a marker naming an id
    absent from the known set fails collection outright. Mirrors the real
    tests/conftest.py::pytest_collection_modifyitems guard, isolated so the
    failure path itself is exercised without breaking the real suite."""

    def test_unknown_id_aborts_the_run(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest(
            """
            import pytest

            KNOWN = frozenset({"FR-01"})

            def pytest_collection_modifyitems(items):
                unknown = [
                    marker.args[0]
                    for item in items
                    for marker in item.iter_markers(name="verifies_requirement")
                    if marker.args[0] not in KNOWN
                ]
                if unknown:
                    raise pytest.UsageError(f"unknown requirement id(s): {unknown}")
            """
        )
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.verifies_requirement("FR-999")
            def test_bogus():
                assert True
            """
        )
        result = pytester.runpytest()
        assert result.ret == pytest.ExitCode.USAGE_ERROR
        result.stderr.fnmatch_lines(["*FR-999*"])

    def test_known_id_collects_and_runs_normally(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest(
            """
            import pytest

            KNOWN = frozenset({"FR-01"})

            def pytest_collection_modifyitems(items):
                unknown = [
                    marker.args[0]
                    for item in items
                    for marker in item.iter_markers(name="verifies_requirement")
                    if marker.args[0] not in KNOWN
                ]
                if unknown:
                    raise pytest.UsageError(f"unknown requirement id(s): {unknown}")
            """
        )
        pytester.makepyfile(
            """
            import pytest

            @pytest.mark.verifies_requirement("FR-01")
            def test_ok():
                assert True
            """
        )
        result = pytester.runpytest()
        result.assert_outcomes(passed=1)
