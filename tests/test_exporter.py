"""FR-24 Claude Code exporter tests — T-EXP-01..02 (added under founder ruling R-ICP)."""

import importlib.util
import sys
from pathlib import Path

from tokenops_cost_auditor.services.ingest import load

FIXTURES = Path(__file__).parent / "fixtures"
EXPORTER = Path(__file__).parents[1] / "scripts" / "exporters" / "claude_code_export.py"


def _load_exporter():  # scripts/ is not a package; load by path
    spec = importlib.util.spec_from_file_location("claude_code_export", EXPORTER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["claude_code_export"] = module
    spec.loader.exec_module(module)
    return module


class TestTEXP01ExportsIngestibleJsonl:
    def test_export_then_ingest(self, tmp_path: Path) -> None:
        exporter = _load_exporter()
        source = tmp_path / "projects" / "proj-a"
        source.mkdir(parents=True)
        (source / "session1.jsonl").write_text((FIXTURES / "claude_code_session.jsonl").read_text())
        out = tmp_path / "export.jsonl"
        count = exporter.export(tmp_path / "projects", out)
        assert count == 40  # one row per assistant message with usage

        frame, report = load(out)
        assert report.valid_pct == 100.0
        assert len(frame) == 40
        assert (frame["provider"] == "anthropic").all()
        assert (frame["endpoint"] == "claude-code").all()
        assert (frame["tag"] == "0a1b2c3d-sess-fixture").all()  # session id as tag
        assert (frame["model"] == "claude-opus-4-8").all()
        assert (frame["prompt_tokens"] > 0).all()
        assert (frame["cached_tokens"] > 0).any()
        assert (frame["cache_write_tokens"] > 0).any()

    def test_empty_source_returns_zero(self, tmp_path: Path) -> None:
        exporter = _load_exporter()
        empty = tmp_path / "nothing"
        empty.mkdir()
        assert exporter.export(empty, tmp_path / "out.jsonl") == 0


class TestTEXP02NoTextInOutput:
    def test_output_carries_no_prompt_or_completion_text(self, tmp_path: Path) -> None:
        """FR-22 at exporter level: fixture content markers must not survive export."""
        exporter = _load_exporter()
        source = tmp_path / "projects"
        source.mkdir()
        (source / "s.jsonl").write_text((FIXTURES / "claude_code_session.jsonl").read_text())
        out = tmp_path / "export.jsonl"
        exporter.export(source, out)
        text = out.read_text()
        assert "SECRET-USER-PROMPT" not in text
        assert "SECRET-ASSISTANT-REPLY" not in text
        assert '"content"' not in text
