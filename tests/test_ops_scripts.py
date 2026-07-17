"""D10 tests — T-OPS-04 (pricing_refresh read-only diff, offline fixture pages)
and daily-digest builder checks (runbook §3; NFR-15 age; FR-29 surfacing)."""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI

from tokenops_cost_auditor.config import Settings

SCRIPTS = Path(__file__).parents[1] / "scripts"
FIXTURE_PAGE = Path(__file__).parent / "fixtures" / "pricing_pages" / "anthropic_fixture.html"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestTOPS04PricingRefresh:
    def test_diff_on_fixture_page_lists_new_changed_and_never_writes(self) -> None:
        refresh = load_script("pricing_refresh")
        yaml_before = refresh.PRICES_YAML.read_bytes()

        known = refresh.table_models(refresh.PRICES_YAML.read_text(encoding="utf-8"))
        page = refresh.strip_html(FIXTURE_PAGE.read_text(encoding="utf-8"))
        assert "$999" not in page  # script/style stripped

        candidates = refresh.extract_candidates(page, known)
        assert "claude-nova-6" in candidates["new_ids"]  # new model surfaced
        assert candidates["found"]["claude-fable-5"] == [10.00, 50.00]

        lines = "\n".join(refresh.diff_lines("fixture://anthropic", candidates, known))
        # table has sonnet-5 at intro 2.00/10.00; the page shows 3.00/15.00 -> mismatch
        assert "claude-sonnet-5" in lines and "VERIFY BY HAND" in lines
        assert "claude-nova-6" in lines
        # fable-5 rates match the table -> must NOT be flagged
        assert "claude-fable-5: page" not in lines

        assert refresh.PRICES_YAML.read_bytes() == yaml_before  # NEVER writes (FR-29)

    def test_source_urls_parsed_from_comments(self) -> None:
        refresh = load_script("pricing_refresh")
        urls = refresh.source_urls(refresh.PRICES_YAML.read_text(encoding="utf-8"))
        assert len(urls) >= 2 and all(u.startswith("https://") for u in urls)

    def test_status_file_failure_roundtrip(self, tmp_path: Path) -> None:
        """FR-29: refresh failures land in a status file the digest can surface."""
        refresh = load_script("pricing_refresh")
        refresh.write_status(tmp_path, ok=False, error="2 source page(s) unreachable")
        status = json.loads((tmp_path / ".ops" / "pricing_refresh.json").read_text())
        assert status["ok"] is False and "unreachable" in status["error"]


class TestDailyDigest:
    def test_digest_sections_and_alerts(self, app: FastAPI, settings: Settings) -> None:
        digest = load_script("daily_digest")
        from test_runner import seed_audit

        audit_id = seed_audit(app, "openai_small.jsonl", email="digest@example.com")
        app.state.runner.run(audit_id)
        now = datetime.now(UTC)
        with app.state.session_factory() as session:
            body = digest.build_digest(session, settings, now=now)

        assert "Audits (24h): 1" in body
        assert "Purges (24h): 0" in body
        assert "no backup dump found" in body  # empty backup dir -> NFR-08 alert

    def test_fresh_backup_clears_alert_and_refresh_failure_surfaces(
        self, app: FastAPI, settings: Settings
    ) -> None:
        digest = load_script("daily_digest")
        backup_dir = Path(settings.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "tokenops_2026-07-17.dump").write_bytes(b"pgdump")

        ops_dir = Path(settings.report_dir) / ".ops"
        ops_dir.mkdir(parents=True, exist_ok=True)
        (ops_dir / "pricing_refresh.json").write_text(
            json.dumps({"ok": False, "ran_at": "2026-07-16T02:00:00+00:00", "error": "boom"})
        )

        with app.state.session_factory() as session:
            body = digest.build_digest(session, settings)
        assert "no backup dump found" not in body
        assert "pricing_refresh FAILED" in body and "boom" in body  # FR-29 surfacing

    def test_stale_pricing_table_alerts(self, app: FastAPI, settings: Settings) -> None:
        """NFR-15: digest carries the pricing-table age; >14d becomes an alert."""
        digest = load_script("daily_digest")
        far_future = datetime.now(UTC) + timedelta(days=365)
        with app.state.session_factory() as session:
            body = digest.build_digest(session, settings, now=far_future)
        assert "Pricing table: last_verified" in body
        assert "STALE" in body and "NFR-15" in body
