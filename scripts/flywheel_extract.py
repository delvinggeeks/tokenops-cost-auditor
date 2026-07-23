"""M-FLY-0 A1 ops CLI — dump the training frame as JSONL to stdout.

Ops tooling, not engine code (NFR-01 untouched). Counts/enums/ids only by
the frame contract; benchmark_sharing=False accounts are excluded at the
source. Usage (runbook ops):

    DATABASE_URL=... SECRET_KEY=... uv run python scripts/flywheel_extract.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services.flywheel import frame


def main() -> int:
    settings = Settings()  # env-driven, like every ops script
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        rows = frame.extract(session, settings.secret_key)
    for row in rows:
        sys.stdout.write(json.dumps(asdict(row), sort_keys=True) + "\n")
    sys.stderr.write(f"{len(rows)} training rows\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
