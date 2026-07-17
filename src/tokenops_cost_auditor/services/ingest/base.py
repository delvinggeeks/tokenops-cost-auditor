"""Ingestion entrypoint: file-level checks, format detection, LogParser protocol
(FR-01). Error taxonomy per docs/03-LLD.md §8 — all messages user-safe."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

ALLOWED_EXTENSIONS = (".jsonl", ".json", ".csv")


class IngestError(Exception):
    """User-facing ingestion failure. kind='format' (whole file) or 'row' (FR-03)."""

    def __init__(self, kind: Literal["format", "row"], message: str) -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class RawRow:
    """One parsed input row, or a per-row parse failure (error is not None)."""

    line_no: int
    data: dict[str, object] | None
    error: str | None = None


class LogParser(Protocol):
    name: str
    provider: str

    def sniff(self, sample_lines: list[str]) -> bool:
        """Return True if the sample lines look like this parser's format."""
        ...

    def parse(self, path: Path) -> Iterator[RawRow]: ...


def check_file(path: Path, max_upload_mb: int) -> None:
    """File-level gates (T-ING-02..04): existence, extension, size, emptiness."""
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise IngestError(
            "format",
            f"unsupported file extension '{path.suffix}' — accepted formats: "
            "OpenAI JSONL export (.jsonl), Anthropic JSONL export (.jsonl), "
            "generic CSV (.csv). See the export guide.",
        )
    size = path.stat().st_size
    if size == 0:
        raise IngestError(
            "format",
            "the uploaded file is empty — expected one JSON object per line (JSONL) "
            "or a CSV with a header row. See the export guide.",
        )
    if size > max_upload_mb * 1024 * 1024:
        raise IngestError(
            "format",
            f"file is {size / (1024 * 1024):.0f}MB — the limit is {max_upload_mb}MB "
            "per upload. Split the export by date range and upload separately.",
        )


def _sample_lines(path: Path, n: int = 5) -> list[str]:
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.strip():
                lines.append(line.strip())
            if len(lines) >= n:
                break
    return lines


def detect_format(path: Path) -> LogParser:
    """Pick a parser by extension + content sniff (T-ING-01)."""
    from tokenops_cost_auditor.services.ingest.anthropic_jsonl import AnthropicJsonlParser
    from tokenops_cost_auditor.services.ingest.generic_csv import GenericCsvParser
    from tokenops_cost_auditor.services.ingest.openai_jsonl import OpenAIJsonlParser

    if path.suffix.lower() == ".csv":
        return GenericCsvParser()

    sample = _sample_lines(path)
    if not sample:
        raise IngestError(
            "format",
            "no data lines found — expected one JSON object per line (JSONL).",
        )
    for parser in (AnthropicJsonlParser(), OpenAIJsonlParser()):
        if parser.sniff(sample):
            return parser
    raise IngestError(
        "format",
        "could not recognize the log format from the file contents — expected an "
        "OpenAI or Anthropic JSONL export, or a generic CSV per the export guide.",
    )


def iter_jsonl(path: Path) -> Iterator[RawRow]:
    """Shared JSONL reader: yields dict rows or per-line errors (never raises per row)."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                yield RawRow(line_no, None, f"invalid JSON: {exc.msg}")
                continue
            if not isinstance(obj, dict):
                yield RawRow(line_no, None, "line is not a JSON object")
                continue
            yield RawRow(line_no, obj)
