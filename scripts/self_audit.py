"""WP-SELF (R-SELF-AUDIT, founder 2026-07-18): audit our own build sessions.

Runs the Claude Code exporter on THIS project's sessions (counts only, FR-22),
runs the CLI audit (the same engine customers get), appends one row to
self_audit/ledger.csv and archives the report JSON. Manual or local-scheduler
runnable; NOT part of the product deployment (ops tooling, engine untouched).

Ledger rows are money-adjacent (R-SELF-AUDIT c): each row lands with
verified="" and may be PUBLISHED (docs chart, launch assets) only after the
founder replaces it with their name — logged like golden files. The docs-site
page renders exclusively founder-verified rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).parents[1]
LEDGER = REPO / "self_audit" / "ledger.csv"
ARCHIVE = REPO / "self_audit" / "reports"  # gitignored; ledger is the record
PROJECT_SESSIONS = (
    Path.home() / ".claude" / "projects" / "-home-lokesh-Desktop-tokenops-cost-auditor"
)

FIELDS = [
    "date",
    "sessions",
    "calls",
    "observed_api_equiv_spend_usd",
    "est_monthly_waste_usd",
    "waste_pct",
    "findings_by_detector",
    "verified",  # founder name after independent check (R-SELF-AUDIT c) — "" = unpublishable
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=PROJECT_SESSIONS)
    args = ap.parse_args()

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    export = ARCHIVE / f"{stamp}_export.jsonl"
    report_json = ARCHIVE / f"{stamp}_report.json"
    pdf = ARCHIVE / f"{stamp}_report.pdf"

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

    report = json.loads(report_json.read_text(encoding="utf-8"))
    summary = report["summary"]
    by_detector: dict[str, int] = {}
    for f in report["findings"]:
        by_detector[f["detector"]] = by_detector.get(f["detector"], 0) + 1
    tags = {
        line.split('"tag": "')[1].split('"')[0]
        for line in export.read_text().splitlines()
        if '"tag": "' in line
    }

    row = {
        "date": stamp,
        "sessions": len(tags),
        "calls": summary["row_count"],
        "observed_api_equiv_spend_usd": round(summary["total_spend_usd"], 2),
        "est_monthly_waste_usd": round(summary["monthly_savings_usd"], 2),
        "waste_pct": round(summary["savings_pct"], 1),
        "findings_by_detector": json.dumps(by_detector, sort_keys=True),
        "verified": "",
    }

    new_file = not LEDGER.exists()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)

    print(f"self-audit row appended to {LEDGER} (verified='' — founder tick required):")
    print("  " + json.dumps(row))
    print(f"report archived: {report_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
