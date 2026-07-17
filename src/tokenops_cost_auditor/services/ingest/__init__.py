"""Ingest service (C2): load(path) -> (CallRecordFrame, ValidationReport)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import structlog

from tokenops_cost_auditor.services.ingest.base import IngestError, check_file, detect_format
from tokenops_cost_auditor.services.ingest.normalizer import normalize
from tokenops_cost_auditor.services.ingest.validator import ValidationReport, build_report

__all__ = ["IngestError", "load"]

log = structlog.get_logger("tokenops_cost_auditor.ingest")

DUP_ID_WARN_PCT = 1.0  # UAT-D5 safety net: same request_id = same call


def _warn_on_duplicate_ids(frame: pd.DataFrame) -> None:
    """UAT-D5 belt-and-braces: an export where the same request_id appears on
    more than 1% of rows almost certainly double-counts calls (one row per
    logger EVENT, not per completed call). The exporter dedupes at the source;
    this warns loudly for foreign logs with the same disease."""
    if len(frame) == 0:
        return
    duplicate_rows = int(frame["request_id"].duplicated().sum())
    pct = 100.0 * duplicate_rows / len(frame)
    if pct > DUP_ID_WARN_PCT:
        log.warning(
            "ingest.duplicate_request_ids",
            duplicate_rows=duplicate_rows,
            total_rows=len(frame),
            pct=round(pct, 1),
            note="same request_id = same call; spend and findings may be inflated (UAT-D5)",
        )


def load(
    path: Path, max_upload_mb: int = 200, prefix_hash_chars: int = 4096
) -> tuple[pd.DataFrame, ValidationReport]:
    """Full FR-01..03 pipeline: file gates -> format detection -> parse -> normalize.
    Callers decide on the report (runner enforces the 95% rule via validator.enforce)."""
    check_file(path, max_upload_mb)
    parser = detect_format(path)
    result = normalize(parser.parse(path), prefix_hash_chars=prefix_hash_chars)
    _warn_on_duplicate_ids(result.frame)
    return result.frame, build_report(result)
