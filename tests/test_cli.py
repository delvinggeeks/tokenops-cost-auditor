"""T-CLI-01 (FR-04): CLI produces a PDF from fixture F1 (docs/05 §3)."""

from pathlib import Path

import pytest

from tokenops_cost_auditor.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.verifies_requirement("FR-04")
class TestTCLI01:
    def test_audit_produces_pdf_and_json(self, tmp_path: Path, capsys) -> None:
        out_pdf = tmp_path / "report.pdf"
        out_json = tmp_path / "report.json"
        code = main(
            [
                "audit",
                str(FIXTURES / "openai_small.jsonl"),
                "--out",
                str(out_pdf),
                "--json",
                str(out_json),
            ]
        )
        assert code == 0
        assert out_pdf.read_bytes().startswith(b"%PDF")
        assert out_json.exists()
        stdout = capsys.readouterr().out
        assert "report written to" in stdout
        assert "estimated savings" in stdout

    def test_bad_input_exits_3(self, tmp_path: Path, capsys) -> None:
        bad = tmp_path / "empty.jsonl"
        bad.touch()
        code = main(["audit", str(bad), "--out", str(tmp_path / "r.pdf")])
        assert code == 3
        assert "audit failed" in capsys.readouterr().err

    def test_dirty_input_reports_row_errors_and_fails(self, tmp_path: Path, capsys) -> None:
        src = (FIXTURES / "mixed_dirty.jsonl").read_bytes()
        f = tmp_path / "dirty.jsonl"
        f.write_bytes(src)
        code = main(["audit", str(f), "--out", str(tmp_path / "r.pdf")])
        assert code == 3
        err = capsys.readouterr().err
        assert "invalid rows" in err  # row-error file surfaced
        assert (tmp_path / "dirty.row_errors.csv").exists()
