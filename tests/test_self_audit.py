"""WP-SELF tests (R-SELF-AUDIT b/c): the docs renderer publishes ONLY
founder-verified ledger rows, and stays MEASUREMENT-PENDING below 3 of them."""

import csv
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load_renderer(tmp_path: Path, rows: list[dict[str, str]]):
    spec = importlib.util.spec_from_file_location(
        "render_self_audit", SCRIPTS / "render_self_audit.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_self_audit"] = module
    spec.loader.exec_module(module)
    ledger = tmp_path / "ledger.csv"
    fields = [
        "date",
        "sessions",
        "calls",
        "observed_api_equiv_spend_usd",
        "est_monthly_waste_usd",
        "waste_pct",
        "findings_by_detector",
        "verified",
    ]
    with ledger.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    module.LEDGER = ledger
    return module


def row(date: str, verified: str = "") -> dict[str, str]:
    return {
        "date": date,
        "sessions": "3",
        "calls": "1000",
        "observed_api_equiv_spend_usd": "100.00",
        "est_monthly_waste_usd": "25.00",
        "waste_pct": "25.0",
        "findings_by_detector": "{}",
        "verified": verified,
    }


class TestWPSelfPublishGate:
    def test_pending_below_three_verified_rows(self, tmp_path: Path) -> None:
        renderer = load_renderer(
            tmp_path,
            [row("2026-07-17", "Lokesh"), row("2026-07-18", "Lokesh"), row("2026-07-19", "")],
        )
        out = renderer.render()
        assert "MEASUREMENT-PENDING" in out
        assert "$" not in out  # no numbers leak from the pending state

    def test_unverified_rows_never_render(self, tmp_path: Path) -> None:
        renderer = load_renderer(
            tmp_path,
            [
                row("2026-07-17", "Lokesh"),
                row("2026-07-18", "Lokesh"),
                row("2026-07-19", "Lokesh"),
                row("2026-07-20", ""),  # unverified — must not appear
            ],
        )
        out = renderer.render()
        assert "MEASUREMENT-PENDING" not in out
        assert "2026-07-19" in out and "2026-07-20" not in out
        assert "3 verified runs" in out
        assert "$300.00" in out  # cumulative from verified rows only
        assert "<svg" in out  # trendline renders
