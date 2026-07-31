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


@pytest.mark.verifies_requirement("FR-01")
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


@pytest.mark.verifies_requirement("FR-01")
class TestTING02OversizeRejected:
    def test_oversize(self, tmp_path: Path) -> None:
        p = tmp_path / "big.jsonl"
        p.write_bytes(b"x" * (2 * 1024 * 1024))
        with pytest.raises(IngestError, match="limit is 1MB"):
            check_file(p, max_upload_mb=1)


@pytest.mark.verifies_requirement("FR-01")
class TestTING03WrongExtensionRejected:
    def test_wrong_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "logs.txt"
        p.write_text("data")
        with pytest.raises(IngestError, match="unsupported file extension"):
            check_file(p, max_upload_mb=200)


@pytest.mark.verifies_requirement("FR-01")
class TestTING04EmptyFile:
    def test_empty_file_actionable(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.jsonl"
        p.touch()
        with pytest.raises(IngestError, match=r"empty.*export guide"):
            check_file(p, max_upload_mb=200)


@pytest.mark.verifies_requirement("FR-02")
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


@pytest.mark.verifies_requirement("FR-02")
class TestPrecomputedPrefixHashPassthrough:
    """Counts-only JSONL shippers may precompute prefix_hash client-side (same
    contract as generic CSV) — honored by both JSONL parsers since D11-12 prep."""

    def test_openai_and_anthropic_wrappers(self, tmp_path: Path) -> None:
        import json

        openai_line = {
            "created": 1750000000,
            "model": "gpt-5.5",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            "id": "req_1",
            "prefix_hash": "a" * 64,
        }
        anthropic_line = {
            "ts": 1750000000,
            "model": "claude-sonnet-5",
            "type": "message",
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "id": "msg_1",
            "prefix_hash": "b" * 64,
        }
        for name, line, expected in (
            ("o.jsonl", openai_line, "a" * 64),
            ("a.jsonl", anthropic_line, "b" * 64),
        ):
            p = tmp_path / name
            p.write_text(json.dumps(line) + "\n", encoding="utf-8")
            frame, report = load(p)
            assert report.valid_pct == 100.0
            assert frame["prefix_hash"].iloc[0] == expected
            # the hash is a first-class column, not a raw_extra leftover
            assert frame["raw_extra"].map(lambda d: "prefix_hash" not in d).all()

    def test_text_still_wins_over_precomputed(self, tmp_path: Path) -> None:
        import json

        line = {
            "created": 1750000000,
            "model": "gpt-5.5",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            "id": "req_1",
            "prefix_hash": "c" * 64,
            "request": {"messages": [{"role": "user", "content": "hello world"}]},
        }
        p = tmp_path / "both.jsonl"
        p.write_text(json.dumps(line) + "\n", encoding="utf-8")
        frame, _ = load(p)
        assert frame["prefix_hash"].iloc[0] != "c" * 64  # computed from text instead


@pytest.mark.verifies_requirement("FR-02")
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


@pytest.mark.verifies_requirement("FR-02")
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


@pytest.mark.verifies_requirement("FR-03")
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


@pytest.mark.verifies_requirement("FR-03")
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


class TestG2ReviewFindings:
    """Regression pins for G2 cold-reviewer findings 1-3 (silent-zero paths)."""

    def test_invalid_cached_tokens_is_row_error_not_zero(self) -> None:
        rows = [
            RawRow(
                1,
                {
                    "provider": "openai",
                    "model": "m",
                    "ts": 1750000000,
                    "prompt_tokens": 100,
                    "completion_tokens": 1,
                    "cached_tokens": "not-a-number",
                },
            ),
            RawRow(
                2,
                {
                    "provider": "openai",
                    "model": "m",
                    "ts": 1750000000,
                    "prompt_tokens": 100,
                    "completion_tokens": 1,
                    "cache_write_tokens": -5,
                },
            ),
        ]
        result = normalize(rows)
        assert len(result.frame) == 0
        assert [e.reason for e in result.row_errors] == [
            "invalid cached_tokens",
            "invalid cache_write_tokens",
        ]

    def test_absent_cache_fields_default_zero(self) -> None:
        rows = [
            RawRow(
                1,
                {
                    "provider": "openai",
                    "model": "m",
                    "ts": 1750000000,
                    "prompt_tokens": 100,
                    "completion_tokens": 1,
                },
            )
        ]
        result = normalize(rows)
        assert result.frame.loc[0, "cached_tokens"] == 0
        assert result.frame.loc[0, "cache_write_tokens"] == 0

    def test_anthropic_float_usage_accepted_invalid_rejected(self, tmp_path: Path) -> None:
        import json

        good = {
            "response": {
                "id": "m1",
                "type": "message",
                "model": "claude-sonnet-5",
                "usage": {
                    "input_tokens": 100.0,
                    "cache_read_input_tokens": 50.0,
                    "cache_creation_input_tokens": 0,
                    "output_tokens": 10,
                },
            },
            "ts": "2026-06-01T00:00:00Z",
        }
        bad = {
            "response": {
                "id": "m2",
                "type": "message",
                "model": "claude-sonnet-5",
                "usage": {"input_tokens": "many", "output_tokens": 10},
            },
            "ts": "2026-06-01T00:00:00Z",
        }
        p = tmp_path / "a.jsonl"
        p.write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
        frame, report = load(p)
        assert len(frame) == 1  # integral floats accepted, garbage rejected
        assert frame.loc[0, "prompt_tokens"] == 150  # 100 + 50 read + 0 write
        assert frame.loc[0, "cached_tokens"] == 50
        assert [e.reason for e in report.errors] == ["missing or invalid prompt_tokens"]

    def test_csv_blank_provider_is_row_error(self, tmp_path: Path) -> None:
        p = tmp_path / "b.csv"
        p.write_text(
            "ts,provider,model,prompt_tokens,completion_tokens\n"
            "2026-06-01T00:00:00Z,,m1,100,10\n"
            "2026-06-01T00:00:00Z,openai,m1,100,10\n"
        )
        frame, report = load(p)
        assert len(frame) == 1
        assert (frame["provider"] == "openai").all()
        assert [e.reason for e in report.errors] == ["missing value for required column 'provider'"]


class TestUATD5DuplicateIdWarning:
    def test_loud_warning_above_one_percent(self, tmp_path: Path) -> None:
        """UAT-D5 safety net: >1% duplicate request_ids warns loudly at load."""
        import json

        lines = [
            {
                "created": 1750000000 + i,
                "model": "gpt-5.5",
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                "id": "req_same" if i < 50 else f"req_{i}",
            }
            for i in range(100)
        ]
        p = tmp_path / "dup.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        import structlog.testing

        with structlog.testing.capture_logs() as logs:
            load(p)
        events = [entry for entry in logs if entry["event"] == "ingest.duplicate_request_ids"]
        assert events and events[0]["duplicate_rows"] == 49  # 50 rows share one id

    def test_no_warning_on_clean_export(self, tmp_path: Path) -> None:
        import json

        lines = [
            {
                "created": 1750000000 + i,
                "model": "gpt-5.5",
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                "id": f"req_{i}",
            }
            for i in range(100)
        ]
        p = tmp_path / "clean.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        import structlog.testing

        with structlog.testing.capture_logs() as logs:
            load(p)
        assert not any(entry["event"] == "ingest.duplicate_request_ids" for entry in logs)
