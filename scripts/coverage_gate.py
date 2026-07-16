"""Coverage gate (docs/04-TRACEABILITY.md coverage rule):
>= 85% lines on services/*, 100% on pricing/coster.py and rules/findings.py.

pytest-cov cannot express split thresholds, so this parses coverage.json.
Paths that do not exist yet are skipped — the gate tightens as packages land.
"""

import json
import sys
from pathlib import Path

SERVICES_PREFIX = "src/tokenops_cost_auditor/services/"
MONEY_FILES = (
    "src/tokenops_cost_auditor/services/pricing/coster.py",
    "src/tokenops_cost_auditor/services/rules/findings.py",
)
SERVICES_MIN_PCT = 85.0


def file_stats(data: dict) -> dict[str, tuple[int, int]]:
    """path -> (covered, total) statement counts."""
    out: dict[str, tuple[int, int]] = {}
    for path, info in data["files"].items():
        s = info["summary"]
        out[path.replace("\\", "/")] = (s["covered_lines"], s["num_statements"])
    return out


def main() -> int:
    cov_path = Path("coverage.json")
    if not cov_path.exists():
        print("coverage.json not found — run pytest with --cov-report=json first")
        return 1
    stats = file_stats(json.loads(cov_path.read_text()))

    failed = False

    svc = [(p, c, t) for p, (c, t) in stats.items() if p.startswith(SERVICES_PREFIX)]
    svc_total = sum(t for _, _, t in svc)
    if svc_total == 0:
        print("services/*: no measurable modules yet — gate skipped (scaffold phase)")
    else:
        pct = 100.0 * sum(c for _, c, _ in svc) / svc_total
        status = "OK" if pct >= SERVICES_MIN_PCT else "FAIL"
        print(f"services/*: {pct:.1f}% (gate {SERVICES_MIN_PCT}%) {status}")
        failed |= pct < SERVICES_MIN_PCT

    for money in MONEY_FILES:
        if money not in stats:
            print(f"{money}: not present yet — gate skipped")
            continue
        covered, total = stats[money]
        pct = 100.0 * covered / total if total else 100.0
        status = "OK" if pct >= 100.0 else "FAIL"
        print(f"{money}: {pct:.1f}% (gate 100%) {status}")
        failed |= pct < 100.0

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
