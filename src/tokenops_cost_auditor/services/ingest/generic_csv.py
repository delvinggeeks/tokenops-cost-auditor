"""Generic CSV parser (FR-01 fallback) — the documented customer-facing contract.

REQUIRED columns (header row, case-insensitive):
    ts, provider, model, prompt_tokens, completion_tokens
OPTIONAL columns:
    cached_tokens, cache_write_tokens, latency_ms, endpoint, request_id, tag,
    declared_max_tokens, prefix_hash
- ts: ISO-8601 (assumed UTC if tz-naive) or unix epoch seconds.
- provider: "openai" | "anthropic" | any lowercase label (used for pricing lookup).
- prompt_tokens is the TOTAL input token count (including any cached portion).
- Text columns (prompt/completion/messages/content/...) are NOT part of the contract
  and are silently dropped — token counts only (FR-22). Precompute prefix_hash
  client-side (SHA-256 hex over the first 4096 prompt chars) to enable cache and
  duplicate detectors.
Unknown extra columns are preserved in raw_extra (FR-02).
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from tokenops_cost_auditor.services.ingest.base import IngestError, RawRow

REQUIRED = ("ts", "provider", "model", "prompt_tokens", "completion_tokens")
OPTIONAL = (
    "cached_tokens",
    "cache_write_tokens",
    "latency_ms",
    "endpoint",
    "request_id",
    "tag",
    "declared_max_tokens",
    "prefix_hash",
)
TEXT_COLUMNS = frozenset(
    {
        "prompt",
        "completion",
        "messages",
        "content",
        "text",
        "system",
        "input",
        "output",
        "response_text",
        "prompt_text",
        "completion_text",
    }
)


class GenericCsvParser:
    name = "generic_csv"
    provider = "generic"

    def sniff(self, sample_lines: list[str]) -> bool:
        return bool(sample_lines) and "prompt_tokens" in sample_lines[0].lower()

    def parse(self, path: Path) -> Iterator[RawRow]:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            header = [h.strip().lower() for h in reader.fieldnames or []]
            missing = [c for c in REQUIRED if c not in header]
            if missing:
                raise IngestError(
                    "format",
                    f"CSV is missing required column(s): {', '.join(missing)}. "
                    f"Required: {', '.join(REQUIRED)} — see the export guide.",
                )
            known = set(REQUIRED) | set(OPTIONAL)
            for line_no, row in enumerate(reader, start=2):  # 1 = header
                clean = {(k or "").strip().lower(): v for k, v in row.items()}
                data: dict[str, object] = {
                    key: clean.get(key) for key in known if clean.get(key) not in (None, "")
                }
                data["provider"] = (str(clean.get("provider", "")) or "generic").lower()
                data["_text"] = None  # text is not part of the CSV contract (FR-22)
                data["_extra"] = {
                    k: v
                    for k, v in clean.items()
                    if k not in known and k not in TEXT_COLUMNS and v not in (None, "")
                }
                yield RawRow(line_no, data)
