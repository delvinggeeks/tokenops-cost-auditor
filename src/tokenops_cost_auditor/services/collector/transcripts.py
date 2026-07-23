"""Claude Code transcript export core (FR-24 / WP-CC-LINK T3).

Lifted verbatim from scripts/exporters/claude_code_export.py so the
installed CLI can ship without the repo (the script is now a thin
wrapper). Counts only by construction — no prompt or completion text
ever enters a row (FR-22); UAT-D5 dedup law: by request_id,
max-complete usage wins, summary returned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def extract_records(transcript: Path) -> list[dict[str, Any]]:
    """Pull one export row per assistant message that reports usage."""
    rows: list[dict[str, Any]] = []
    with transcript.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "assistant":
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict) or "input_tokens" not in usage:
                continue
            rows.append(
                {
                    "request_id": message.get("id"),
                    "ts": entry.get("timestamp"),
                    "endpoint": "claude-code",
                    "tag": str(entry.get("sessionId") or transcript.stem),
                    "response": {
                        "id": message.get("id"),
                        "type": "message",
                        "model": message.get("model"),
                        # counts only — content deliberately omitted (FR-22)
                        "usage": {
                            "input_tokens": int(usage.get("input_tokens") or 0),
                            "cache_creation_input_tokens": int(
                                usage.get("cache_creation_input_tokens") or 0
                            ),
                            "cache_read_input_tokens": int(
                                usage.get("cache_read_input_tokens") or 0
                            ),
                            "output_tokens": int(usage.get("output_tokens") or 0),
                        },
                    },
                }
            )
    return rows


def _completeness(row: dict[str, Any]) -> int:
    usage = row["response"]["usage"]
    return int(sum(usage.values()))


def dedupe_records(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """UAT-D5 (founder verification refusal, 2026-07-18): transcripts emit
    MULTIPLE events per completed API call (streaming updates; session
    continuations replay messages across files), so one export row per event
    double-counts spend. One row per request_id: last-write-wins on usage,
    and if usage tuples differ across events the max-complete one is kept —
    counted once. Rows without an id cannot be deduped and pass through."""
    kept: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    no_id: list[tuple[int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        request_id = row.get("request_id")
        if not request_id:
            no_id.append((index, row))
            continue
        rank = (_completeness(row), index)  # max-complete wins; ties -> latest event
        if request_id not in kept or rank > kept[request_id][0]:
            kept[request_id] = (rank, row)
    ordered = sorted(
        [(rank[1], row) for rank, row in kept.values()] + no_id, key=lambda pair: pair[0]
    )
    unique = [row for _, row in ordered]
    summary = {
        "rows_in": len(rows),
        "unique_out": len(unique),
        "duplicates_dropped": len(rows) - len(unique),
    }
    return unique, summary


def export(source: Path, out: Path) -> int:
    transcripts = sorted(source.rglob("*.jsonl"))
    if not transcripts:
        print(f"no .jsonl transcripts found under {source}", file=sys.stderr)
        return 0
    rows: list[dict[str, Any]] = []
    for transcript in transcripts:
        rows.extend(extract_records(transcript))
    unique, summary = dedupe_records(rows)
    with out.open("w", encoding="utf-8") as fh:
        for row in unique:
            fh.write(json.dumps(row) + "\n")
    # UAT-D5: the operator sees the dedup arithmetic on every run
    print(
        f"dedup: rows_in={summary['rows_in']} unique_out={summary['unique_out']} "
        f"duplicates_dropped={summary['duplicates_dropped']}"
    )
    print(
        f"wrote {summary['unique_out']} call records from {len(transcripts)} "
        f"session file(s) to {out}"
    )
    return summary["unique_out"]
