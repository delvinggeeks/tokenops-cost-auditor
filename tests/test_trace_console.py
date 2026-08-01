"""T-TRC-01..07 — LE-9 traceability console (scripts/trace.py).

The console's whole value is that it does NOT raise false defects, so these tests pin
both directions: a real break must be reported, and an informal matrix cell must NOT be
reported. Parsing and status are pure, so no server and no network are involved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import trace as tc


class TestRangeExpansion:
    def test_t_trc_01_range_expands_inclusive_and_width_preserving(self) -> None:
        """T-TRC-01: 'T-ING-01..04' is four ids, zero-padded as written."""
        out = tc.expand_ranges("T-ING-01..04")
        assert out.split() == ["T-ING-01", "T-ING-02", "T-ING-03", "T-ING-04"]

    def test_t_trc_02_non_range_text_is_untouched(self) -> None:
        """T-TRC-02: a bare id and prose survive expansion unchanged."""
        assert tc.expand_ranges("T-API-01 (manual)") == "T-API-01 (manual)"


class TestParsing:
    def test_t_trc_03_requirements_carry_id_priority_and_title(self) -> None:
        """T-TRC-03: docs/01 lines yield id + priority, with the provenance tag dropped."""
        reqs = tc.parse_requirements(
            "FR-07 (M) Detector D1 oversized-model.\n"
            "FR-38 (S) [pillar-map 2026-07-28] Showback export.\n"
            "not a requirement line\n"
        )
        assert set(reqs) == {"FR-07", "FR-38"}
        assert reqs["FR-07"].priority == "M"
        assert reqs["FR-38"].title.startswith("Showback export")

    def test_t_trc_04_matrix_row_expands_its_test_range(self) -> None:
        """T-TRC-04: the matrix's 'T-ING-01..04' becomes four claimed ids."""
        rows = tc.parse_matrix(
            "| FR-01  | C1,C2 | web/upload, ingest/* | T-ING-01..04, T-API-01 | quickstart |"
        )
        assert rows["FR-01"]["tests"] == [
            "T-API-01",
            "T-ING-01",
            "T-ING-02",
            "T-ING-03",
            "T-ING-04",
        ]


class TestStatus:
    def _req(self, **kw: object) -> tc.Requirement:
        base = {"id": "FR-99", "priority": "M", "title": "t", "in_matrix": True}
        return tc.Requirement(**{**base, **kw})  # type: ignore[arg-type]

    def test_t_trc_05_status_reflects_the_walk(self) -> None:
        """T-TRC-05: no row and no resolvable test are RED; a partial break is AMBER."""
        assert self._req(in_matrix=False).status == "red"
        assert self._req(claimed_tests=["T-A-01"], dead_tests=["T-A-01"]).status == "red"
        assert (
            self._req(
                claimed_tests=["T-A-01", "T-A-02"],
                resolved_tests=["T-A-01"],
                dead_tests=["T-A-02"],
            ).status
            == "amber"
        )
        assert self._req(claimed_tests=["T-A-01"], resolved_tests=["T-A-01"]).status == "green"

    def test_t_trc_06_advisory_module_drift_never_downgrades_status(self) -> None:
        """T-TRC-06: module cells are informal prose, so they must not drive status —
        otherwise the console cries wolf and stops being trusted."""
        r = self._req(
            claimed_tests=["T-A-01"], resolved_tests=["T-A-01"], missing_modules=["web/upload"]
        )
        assert r.status == "green"


class TestModuleResolution:
    @pytest.mark.parametrize(
        "cell",
        [
            "Ops",  # bare label
            "/breakdown",  # URL route, not a file
            "rules/findings(EvidenceRef)",  # prose with parens
            "docs/15); trigger-gated",  # prose fragment from a comma split
            "services/dashboard/showback.render_csv (LLD §9.5 header `dimension",
        ],
    )
    def test_t_trc_07_unfalsifiable_cells_are_never_reported_missing(self, cell: str) -> None:
        """T-TRC-07: only a clean path-shaped cell is falsifiable. Everything else is
        reported present — a false defect is worse than a missed one here."""
        assert tc.module_exists(cell) is True

    def test_t_trc_07b_real_module_paths_resolve_under_services(self) -> None:
        """T-TRC-07b: the matrix writes 'rules/d1_oversized_model', which lives under
        services/ — resolution must try every package root, not assume one."""
        assert tc.module_exists("rules/d1_oversized_model") is True
        assert tc.module_exists("pricing/coster") is True
        assert tc.module_exists("definitely/not/a/real/module") is False


class TestIndexAgainstTheLiveRepo:
    def test_t_trc_08_index_builds_and_totals_are_self_consistent(self) -> None:
        """T-TRC-08: totals must add up — a dashboard that miscounts is worthless."""
        idx = tc.build_index()
        t = idx["totals"]
        reqs = idx["requirements"]
        assert t["requirements"] == len(reqs)
        assert t["green"] + t["amber"] + t["red"] == t["requirements"]
        assert t["in_matrix"] + t["untraced"] == t["requirements"]
        assert t["dead_test_ids"] >= 0 and t["unclaimed_tests"] >= 0

    def test_t_trc_09_render_status_is_pure_text(self) -> None:
        """T-TRC-09: render_status formats without a server (the loop_status precedent)."""
        out = tc.render_status(tc.build_index())
        assert "requirements declared" in out
        assert "UNCLAIMED (invisible)" in out
