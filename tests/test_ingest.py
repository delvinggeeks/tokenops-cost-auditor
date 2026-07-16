"""D2 ingest tests — T-ING-01..09 (docs/05-TEST-PLAN.md §3)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tokenops_cost_auditor.services import ingest
from tokenops_cost_auditor.services.ingest import IngestError, load
from tokenops_cost_auditor.services.ingest.base import RawRow, check_file, detect_format
from tokenops_cost_auditor.services.ingest.normalizer import COLUMNS, normalize
from tokenops_cost_auditor.services.ingest.validator import build_report, enforce, write_error_file

FIXTURES = Path(__file__).parent / "fixtures"
F1 = FIXTURES / "openai_small.jsonl"
F2 = FIXTURES / "anthropic_small.jsonl"
F3 = FIXTURES / "mixed_dirty.jsonl"
F4 = FIXTURES / "generic.csv"


class TestTING01FormatDetection:
    def test_openai_detected(self) -> None:
        assert detect_format(F1).name == "openai_jsonl"

    def test_anthropic_detected(self) -> None:
        assert detect_format(F2).name == "anthropic_jsonl"

    def test_csv_detected(self) -> None:
        assert detect_format(F4).name == "generic_csv"

    def test_unrecognizable_jsonl_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "junk.jsonl"
        p.write_text('{"foo": 1}\n{"bar": 2}\n')
        with pytest.raises(IngestError, match="could not recognize"):
            detect_format(p)


class TestTING02OversizeRejected:
    def test_oversize(self, tmp_path: Path) -> None:
        p = tmp_path / "big.jsonl"
        p.write_bytes(b"x" * (2 * 1024 * 1024))
        with pytest.raises(IngestError, match="limit is 1MB"):
            check_file(p, max_upload_mb=1)


class TestTING03WrongExtensionRejected:
    def test_wrong_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "logs.txt"
        p.write_text("data")
        with pytest.raises(IngestError, match="unsupported file extension"):
            check_file(p, max_upload_mb=200)


class TestTING04EmptyFile:
    def test_empty_file_actionable(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.jsonl"
        p.touch()
        with pytest.raises(IngestError, match=r"empty.*export guide"):
            check_file(p, max_upload_mb=200)


class TestTING05ColumnMapping:
    def test_openai_mapping(self) -> None:
        frame, report = load(F1)
        assert list(frame.columns) == list(COLUMNS)
        assert report.valid_pct == 100.0
        assert len(frame) == 500
        assert (frame["provider"] == "openai").all()
        assert frame["model"].str.startswith("gpt").all()
        assert (frame["prompt_tokens"] > 0).all()
        assert (frame["cached_tokens"] <= frame["prompt_tokens"]).all()
        assert (frame["cache_write_tokens"] == 0).all()  # OpenAI: no separate writes
        assert frame["prefix_hash"].notna().all()  # messages present in F1
        assert frame["declared_max_tokens"].notna().all()

    def test_anthropic_mapping_total_prompt_semantics(self) -> None:
        frame, report = load(F2)
        assert report.valid_pct == 100.0
        assert (frame["provider"] == "anthropic").all()
        # prompt_tokens = input + cache_read + cache_write (R-Q4 total semantics)
        assert (
            frame["prompt_tokens"] >= frame["cached_tokens"] + frame["cache_write_tokens"]
        ).all()
        assert (frame["cached_tokens"] > 0).any()
        assert (frame["cache_write_tokens"] > 0).any()

    def test_csv_mapping(self) -> None:
        frame, report = load(F4)
        assert report.valid_pct == 100.0
        assert len(frame) == 300
        assert set(frame["provider"].unique()) <= {"openai", "anthropic"}
        assert frame["request_id"].str.startswith("csv-").all()


class TestTING06RawExtraPreserved:
    def test_openai_unknown_field_preserved(self) -> None:
        frame, _ = load(F1)
        assert frame["raw_extra"].map(lambda d: d.get("team")).notna().all()

    def test_csv_unknown_column_preserved_and_no_text(self) -> None:
        frame, _ = load(F4)
        assert frame["raw_extra"].map(lambda d: "cost_center" in d).all()

    def test_text_never_in_frame(self) -> None:
        """FR-22: no column or raw_extra key carries prompt text."""
        frame, _ = load(F1)
        assert "_text" not in frame.columns
        forbidden = {"messages", "content", "prompt", "completion", "text", "system"}
        assert frame["raw_extra"].map(lambda d: not (set(d) & forbidden)).all()


class TestTING07UTCCoercion:
    def test_epoch_and_naive_and_offset(self) -> None:
        rows = [
            RawRow(
                1,
                {
                    "provider": "openai",
                    "model": "m",
                    "ts": 1750000000,
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                },
            ),
            RawRow(
                2,
                {
                    "provider": "openai",
                    "model": "m",
                    "ts": "2026-06-01T10:00:00",
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                },
            ),
            RawRow(
                3,
                {
                    "provider": "openai",
                    "model": "m",
                    "ts": "2026-06-01T15:30:00+05:30",
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                },
            ),
        ]
        result = normalize(rows)
        assert result.frame["ts"].dt.tz is not None
        assert str(result.frame["ts"].dt.tz) == "UTC"
        assert result.frame.loc[0, "ts"] == datetime.fromtimestamp(1750000000, tz=UTC)
        assert result.frame.loc[1, "ts"] == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        assert result.frame.loc[2, "ts"] == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)


class TestTING08DirtyFixtureErrorFile:
    def test_row_error_file_contents(self, tmp_path: Path) -> None:
        _frame, report = load(F3)
        assert report.total_rows == 500
        assert len(report.errors) == 40  # exactly 8% engineered invalid
        assert report.valid_pct == pytest.approx(92.0)
        error_file = write_error_file(report, tmp_path / "row_errors.csv")
        content = error_file.read_text()
        assert content.startswith("line_no,reason")
        assert len(content.strip().splitlines()) == 41  # header + one per error
        assert "invalid JSON" in content
        assert "missing or invalid timestamp" in content
        assert "missing or invalid prompt_tokens" in content


class TestTING09Below95Aborts:
    def test_dirty_fixture_aborts(self) -> None:
        _, report = load(F3)  # 92% valid < 95%
        with pytest.raises(IngestError, match=r"92\.0% of rows are valid"):
            enforce(report)

    def test_clean_fixture_passes(self) -> None:
        _, report = load(F1)
        enforce(report)  # no raise

    def test_zero_rows_aborts(self, tmp_path: Path) -> None:
        rows: list[RawRow] = []
        report = build_report(normalize(rows))
        with pytest.raises(IngestError, match="no data rows"):
            enforce(report)


def test_load_is_package_api() -> None:
    assert ingest.load is load
