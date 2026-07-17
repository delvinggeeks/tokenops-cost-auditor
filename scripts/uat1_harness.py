"""UAT-1 harness (docs/05 §5; founder ruling R-D11-12-PARTIAL).

One command for the founder-executed dogfood audit: export local Claude Code
sessions (counts only, FR-24) -> run the CLI audit (same engine as the
service) -> emit PDF + JSON + a per-finding REVIEW SHEET to fill in by hand.
The build cannot self-certify UAT-1; this harness only makes the founder's
manual review fast and complete.

Usage:
    uv run python scripts/uat1_harness.py [--source ~/.claude/projects]
                                          [--out-dir uat1]

Exit criteria under review (docs/05 §5) — recorded on the sheet:
  1. zero false-positive findings judged embarrassing
  2. report readable by a non-founder CTO in < 10 minutes
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=Path.home() / ".claude" / "projects")
    ap.add_argument("--out-dir", type=Path, default=Path("uat1"))
    args = ap.parse_args()
    out: Path = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    export = out / "claude_code_export.jsonl"
    pdf = out / "report.pdf"
    report_json = out / "report.json"

    print("[1/3] exporting Claude Code sessions (token counts only, FR-24)")
    subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "exporters" / "claude_code_export.py"),
            "--source",
            str(args.source),
            "--out",
            str(export),
        ],
        check=True,
    )

    print("[2/3] auditing with the CLI (same engine as the service, FR-04)")
    subprocess.run(
        [
            "uv",
            "run",
            "tokenops-cost-auditor",
            "audit",
            str(export),
            "--out",
            str(pdf),
            "--json",
            str(report_json),
        ],
        check=True,
        cwd=REPO,
    )

    print("[3/3] writing the review sheet")
    report = json.loads(report_json.read_text(encoding="utf-8"))
    sheet = out / "uat1_review_sheet.csv"
    with sheet.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "finding_id",
                "detector",
                "severity",
                "confidence",
                "monthly_usd",
                "fix_text",
                "verdict (ok / false-positive / embarrassing-FP)",
                "notes (threshold knob to turn? see runbook §8a)",
            ]
        )
        for f in report.get("findings", []):
            writer.writerow(
                [
                    f.get("id"),
                    f.get("detector"),
                    f.get("severity"),
                    f.get("confidence"),
                    f.get("monthly_cost_impact_usd"),
                    str(f.get("fix_text", ""))[:120],
                    "",
                    "",
                ]
            )

    print(
        f"""
UAT-1 artifacts ready in {out}/:
  report.pdf              read first, as a CTO would — time yourself (<10 min?)
  report.json             deterministic artifact
  uat1_review_sheet.csv   one row per finding — fill verdict + notes

Exit criteria (docs/05 §5, founder-certified only):
  [ ] zero false-positive findings judged embarrassing
  [ ] report readable by a non-founder CTO in < 10 minutes
Calibration: knob table in docs/06-OPS-RUNBOOK.md §8a; defaults changes are
money-math discipline (golden update + spreadsheet diff, CLAUDE.md rule 4).
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
