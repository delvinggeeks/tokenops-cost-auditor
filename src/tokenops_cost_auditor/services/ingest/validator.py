"""Row validation report + the >=95%-valid gate (FR-03, T-ING-08..09)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from tokenops_cost_auditor.services.ingest.base import IngestError
from tokenops_cost_auditor.services.ingest.normalizer import NormalizeResult, RowError

MIN_VALID_PCT = 95.0  # FR-03


@dataclass(frozen=True)
class ValidationReport:
    total_rows: int
    valid_rows: int
    errors: tuple[RowError, ...]

    @property
    def valid_pct(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return 100.0 * self.valid_rows / self.total_rows


def build_report(result: NormalizeResult) -> ValidationReport:
    return ValidationReport(
        total_rows=result.total_rows,
        valid_rows=len(result.frame),
        errors=tuple(result.row_errors),
    )


def write_error_file(report: ValidationReport, path: Path) -> Path:
    """Downloadable per-row error file (FR-03): line_no,reason CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["line_no", "reason"])
        for err in report.errors:
            writer.writerow([err.line_no, err.reason])
    return path


def enforce(report: ValidationReport, error_file: Path | None = None) -> None:
    """Abort the audit when validity falls below the FR-03 floor."""
    if report.total_rows == 0:
        raise IngestError("row", "no data rows could be read from the file.")
    if report.valid_pct < MIN_VALID_PCT:
        where = f" Row-error file: {error_file.name}." if error_file else ""
        raise IngestError(
            "row",
            f"only {report.valid_pct:.1f}% of rows are valid — the audit requires "
            f">= {MIN_VALID_PCT:.0f}%. Fix the rows listed in the error report and "
            f"re-upload.{where}",
        )
