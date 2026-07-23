"""Claude Code local-log exporter (FR-24, R-ICP) — thin wrapper.

The core moved to tokenops_cost_auditor.services.collector.transcripts at
WP-CC-LINK so the installed CLI ships without the repo. Same flags, same
counts-only output, same UAT-D5 dedup summary.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tokenops_cost_auditor.services.collector.transcripts import export


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Claude Code transcripts to TokenOps JSONL (counts only)"
    )
    parser.add_argument("--source", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--out", type=Path, default=Path("claude_code_usage.jsonl"))
    args = parser.parse_args()
    written = export(args.source, args.out)
    print(f"wrote {written} rows to {args.out} (counts only — no text)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
