"""Ingest service (C2): load(path) -> (CallRecordFrame, ValidationReport)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tokenops_cost_auditor.services.ingest.base import IngestError, check_file, detect_format
from tokenops_cost_auditor.services.ingest.normalizer import normalize
from tokenops_cost_auditor.services.ingest.validator import ValidationReport, build_report

__all__ = ["IngestError", "load"]


def load(
    path: Path, max_upload_mb: int = 200, prefix_hash_chars: int = 4096
) -> tuple[pd.DataFrame, ValidationReport]:
    """Full FR-01..03 pipeline: file gates -> format detection -> parse -> normalize.
    Callers decide on the report (runner enforces the 95% rule via validator.enforce)."""
    check_file(path, max_upload_mb)
    parser = detect_format(path)
    result = normalize(parser.parse(path), prefix_hash_chars=prefix_hash_chars)
    return result.frame, build_report(result)
