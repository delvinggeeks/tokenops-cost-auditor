"""T-PERF-01 (NFR-04): 1M-row JSONL through the full analysis pipeline in
< 10 minutes. Marked `perf` — nightly CI or manual trigger only (docs/05 §4;
founder ruling R-PERF-MANUAL). Prints per-stage timings and peak RSS so the
docs-site performance page (MP-6) can quote a measured run."""

import gzip
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services import ingest
from tokenops_cost_auditor.services.pricing import coster
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import observed_days
from tokenops_cost_auditor.services.rules.registry import run_all

REPO = Path(__file__).parents[1]
FIXTURE_GZ = REPO / "tests" / "fixtures" / "perf_1m.jsonl.gz"
WALL_CLOCK_BOUND_S = 600  # NFR-04: < 10 min on a 4-vCPU VPS
ROWS = 1_000_000


@pytest.mark.perf
@pytest.mark.verifies_requirement("NFR-04")
class TestTPERF01:
    def test_1m_rows_under_wall_clock_bound(self, tmp_path: Path) -> None:
        if not FIXTURE_GZ.exists():  # F7 is generated, not committed (docs/05 §2)
            subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts" / "gen_perf_fixture.py"),
                    "--rows",
                    str(ROWS),
                    "--out",
                    str(FIXTURE_GZ),
                ],
                check=True,
            )
        jsonl = tmp_path / "perf_1m.jsonl"
        with gzip.open(FIXTURE_GZ, "rb") as src, jsonl.open("wb") as dst:
            shutil.copyfileobj(src, dst)

        timings: dict[str, float] = {}
        started = time.perf_counter()

        t0 = time.perf_counter()
        frame, report = ingest.load(jsonl, max_upload_mb=2000)
        timings["ingest+normalize"] = time.perf_counter() - t0
        assert len(frame) == ROWS and report.valid_pct == 100.0

        t0 = time.perf_counter()
        table = PricingTable.load()
        priced, unpriced = coster.apply(table, frame)
        total = coster.total_spend(priced)
        coster.reconcile(priced, total)  # NFR-07 property holds at scale
        timings["price+reconcile"] = time.perf_counter() - t0
        assert unpriced == []

        t0 = time.perf_counter()
        settings = Settings(_env_file=None)
        ctx = DetectorContext(settings=settings, table=table, observed_days=observed_days(priced))
        findings = run_all(priced, ctx)
        timings["detect (D1-D6)"] = time.perf_counter() - t0
        assert findings, "planted waste must be found at scale"

        t0 = time.perf_counter()
        model = ReportModel.build(
            audit_id="perf-run",
            priced=priced,
            findings=findings,
            unpriced=unpriced,
            table=table,
            generated_at=None,
        )
        render_json(model, tmp_path / "report.json")
        timings["assemble+render_json"] = time.perf_counter() - t0

        wall = time.perf_counter() - started
        peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(f"\nT-PERF-01 wall-clock: {wall:.1f}s (bound {WALL_CLOCK_BOUND_S}s)")
        for stage, seconds in timings.items():
            print(f"  {stage:<22} {seconds:8.1f}s")
        print(f"  peak RSS: {peak_rss_mb:.0f} MB; findings: {len(findings)}")
        assert wall < WALL_CLOCK_BOUND_S
