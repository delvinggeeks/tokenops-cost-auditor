"""T-DASH-01..05 + T-HELP-01..07 + design-asset pinning (PLAN-V15 V-D4/V-D4g).

Covers R-PERSONA (three depths, jargon law) and R-CLARITY (fixed depth-(c)
order, live thresholds, purpose lines) as executable rules, not review notes.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    Audit,
    FindingFeedback,
    FindingRow,
    User,
)
from tokenops_cost_auditor.web import help as help_registry

EMAIL = "owner@example.com"
HDR = {"X-User-Email": EMAIL}
DETECTOR_IDS = re.compile(r"\b(d[1-6]_[a-z_]+|D[1-6])\b")
TAGS = re.compile(r"<[^>]+>")


def visible_text(html: str) -> str:
    """What the user actually reads — the jargon law governs copy, not the
    finding ids that necessarily appear in URLs and form values."""
    return TAGS.sub(" ", html)


def seed_audit(
    app: FastAPI,
    *,
    findings: list[tuple[str, str, float]],
    days: int = 30,
    when: datetime | None = None,
) -> str:
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL)
            session.add(user)
            session.flush()
        audit = Audit(
            user_id=user.id,
            status="done",
            observed_days=days,
            row_count=5000,
            total_spend_usd=900.0,
            savings_pct=24.1,
            created_at=when or datetime.now(UTC),
            report_ready_at=when or datetime.now(UTC),
        )
        session.add(audit)
        session.flush()
        for fid, det, usd in findings:
            session.add(
                FindingRow(
                    audit_id=audit.id,
                    finding_id=fid,
                    detector=det,
                    severity="high",
                    monthly_impact_usd=usd,
                    confidence="estimated",
                    fix_text="set cache_control",
                    evidence_sample=[
                        {
                            "row_idx": 1,
                            "ts": "2026-07-18T09:14:02Z",
                            "model": "claude-sonnet-5",
                            "tokens": 28412,
                            "note": "uncached",
                        }
                    ],
                )
            )
        session.commit()
        return audit.id


class TestDashboard:
    def test_01_auth_required(self, app: FastAPI) -> None:
        assert TestClient(app).get("/dashboard").status_code == 401

    def test_02_zero_state_is_honest(self, app: FastAPI) -> None:
        """T-DASH-05: no audits -> no invented numbers, and the empty state
        teaches the next action (R-Q9 + R-DESIGN-SHELL §2)."""
        page = TestClient(app).get("/dashboard", headers=HDR)
        assert page.status_code == 200
        assert "Connect a source" in page.text
        assert "$0.00" not in page.text  # never show a fabricated zero headline
        assert "Your first audit fills this in" in page.text

    def test_03_headline_and_widgets_render(self, app: FastAPI) -> None:
        seed_audit(
            app,
            findings=[
                ("D2-001", "d2_missing_cache", 1120.10),
                ("D1-001", "d1_oversized_model", 688.75),
            ],
        )
        page = TestClient(app).get("/dashboard", headers=HDR)
        assert page.status_code == 200
        # identified (not yet applied) shows as an estimate, never as savings
        assert "1,808.85" in page.text and "identified (estimate)" in page.text
        for wid in (
            "w-savings",
            "w-spend_trend",
            "w-waste_trend",
            "w-top_findings",
            "w-sources",
            "w-next_audit",
        ):
            assert f'id="{wid}"' in page.text
        assert 'id="pipeline-ribbon"' in page.text

    def test_04_widget_partials_render_standalone(self, app: FastAPI) -> None:
        """Every widget is independently htmx-refreshable."""
        seed_audit(app, findings=[("D2-001", "d2_missing_cache", 500.0)])
        client = TestClient(app)
        for key in (
            "savings",
            "spend_trend",
            "waste_trend",
            "top_findings",
            "sources",
            "next_audit",
        ):
            r = client.get(f"/dashboard/w/{key}", headers=HDR)
            assert r.status_code == 200, key
            assert "<section" in r.text and "provenance" in r.text
        assert client.get("/dashboard/w/nope", headers=HDR).status_code == 404

    def test_05_auth_scoping_no_cross_user_leak(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, findings=[("D2-001", "d2_missing_cache", 999.0)])
        other = TestClient(app).get("/dashboard", headers={"X-User-Email": "someone@else.com"})
        assert "999" not in other.text
        drawer = TestClient(app).get(
            f"/findings/{audit_id}/D2-001", headers={"X-User-Email": "someone@else.com"}
        )
        assert drawer.status_code == 404


class TestFindingsAndFeedback:
    def test_01_table_uses_plain_language_only(self, app: FastAPI) -> None:
        """R-PERSONA jargon law: no detector identifier at headline depth."""
        seed_audit(app, findings=[("D2-001", "d2_missing_cache", 1120.10)])
        page = TestClient(app).get("/findings", headers=HDR)
        assert page.status_code == 200
        assert "paying full price for prompts you send again and again" in page.text
        table_text = visible_text(page.text.split('id="drawer"')[0])
        assert not DETECTOR_IDS.search(table_text), "detector id leaked to headline depth"

    def test_02_drawer_is_depth_c_in_fixed_order(self, app: FastAPI) -> None:
        """R-CLARITY §1: why -> evidence -> fix -> verify -> methodology."""
        audit_id = seed_audit(app, findings=[("D2-001", "d2_missing_cache", 1120.10)])
        r = TestClient(app).get(f"/findings/{audit_id}/D2-001", headers=HDR)
        assert r.status_code == 200
        order = [
            r.text.index(s)
            for s in (
                "Why this was flagged",
                "Evidence",
                "The fix",
                "How you'll know it worked",
                "Methodology",
            )
        ]
        assert order == sorted(order), "depth (c) sections out of order"
        # technical identifier is allowed HERE and only here
        assert "d2_missing_cache" in r.text
        # threshold values come from live Settings (T-HELP-06)
        assert "25 times" in r.text or "25 " in r.text

    def test_03_feedback_captures_and_updates_headline(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, findings=[("D2-001", "d2_missing_cache", 1120.10)])
        client = TestClient(app)
        r = client.post(
            f"/findings/{audit_id}/D2-001/feedback", headers=HDR, data={"verdict": "applied"}
        )
        assert r.status_code == 200
        assert 'id="w-savings"' in r.text  # the savings widget swaps back in
        with app.state.session_factory() as session:
            fb = session.execute(select(FindingFeedback)).scalars().one()
            assert fb.verdict == "applied" and fb.actor == EMAIL
        # idempotent re-vote updates in place
        client.post(
            f"/findings/{audit_id}/D2-001/feedback", headers=HDR, data={"verdict": "dismissed"}
        )
        with app.state.session_factory() as session:
            rows = session.execute(select(FindingFeedback)).scalars().all()
            assert len(rows) == 1 and rows[0].verdict == "dismissed"

    def test_04_bad_verdict_rejected(self, app: FastAPI) -> None:
        audit_id = seed_audit(app, findings=[("D2-001", "d2_missing_cache", 1.0)])
        r = TestClient(app).post(
            f"/findings/{audit_id}/D2-001/feedback", headers=HDR, data={"verdict": "sabotage"}
        )
        assert r.status_code == 400


class TestTourAndGuide:
    def test_01_tour_shows_once_and_dismissal_persists(self, app: FastAPI) -> None:
        client = TestClient(app)
        assert 'id="tour"' in client.get("/dashboard", headers=HDR).text
        assert client.post("/tour/dismiss", headers=HDR).status_code == 200
        assert 'id="tour"' not in client.get("/dashboard", headers=HDR).text
        # replay resets it
        client.post("/tour/replay", headers=HDR, follow_redirects=False)
        assert 'id="tour"' in client.get("/dashboard", headers=HDR).text

    def test_02_guide_pages_carry_audience_tags(self, app: FastAPI) -> None:
        client = TestClient(app)
        index = client.get("/guide", headers=HDR)
        assert index.status_code == 200 and "Who this is for" in index.text
        for page in help_registry.guide_index():
            r = client.get(f"/guide/{page['slug']}", headers=HDR)
            assert r.status_code == 200
            assert f"<strong>{page['audience']}</strong>" in r.text
        assert client.get("/guide/nope", headers=HDR).status_code == 404


class TestHelpRegistry:
    def test_01_every_widget_has_help(self) -> None:
        for key in (
            "pipeline",
            "verified_savings",
            "spend_trend",
            "waste_share",
            "top_findings",
            "sources",
            "next_audit",
            "alerts",
            "statement",
        ):
            h = help_registry.widget(key)
            assert {"title", "tells", "what", "where", "do", "link", "link_text"} <= set(h)
        with pytest.raises(KeyError):
            help_registry.widget("does_not_exist")

    def test_05_every_detector_has_the_full_triple(self) -> None:
        s = Settings(secret_key="k" * 64, database_url="sqlite://", _env_file=None)
        keys = help_registry.detector_keys()
        assert len(keys) == 6
        for key in keys:
            h = help_registry.detector(key, s)
            assert h.plain and h.why and h.fix and h.verify and h.methodology_url
            # jargon law: the plain phrasing must not contain a detector id
            assert not DETECTOR_IDS.search(h.plain), key

    def test_06_thresholds_render_from_settings_not_hardcoded(self) -> None:
        """Changing a threshold must change the help text."""
        base = Settings(secret_key="k" * 64, database_url="sqlite://", _env_file=None)
        tuned = Settings(
            secret_key="k" * 64, database_url="sqlite://", d2_cache_min_repeats=99, _env_file=None
        )
        assert "25" in help_registry.detector("d2_missing_cache", base).why
        assert "99" in help_registry.detector("d2_missing_cache", tuned).why

    def test_07_every_destination_has_a_purpose_line(self) -> None:
        for dest in (
            "overview",
            "findings",
            "sources",
            "get_logs",
            "alerts",
            "statements",
            "guide",
            "settings",
            "billing",
        ):
            assert help_registry.purpose(dest).endswith(".")


class TestDesignAssets:
    def test_served_css_matches_the_design_source(self) -> None:
        """The shipped stylesheet and the design source cannot drift."""
        served = Path("src/tokenops_cost_auditor/web/static/wa-design.css").read_text()
        source = Path("design/wa-design.css").read_text()
        assert served == source, "run: cp design/wa-design.css src/.../web/static/"

    def test_sprite_matches_the_design_source(self) -> None:
        sprite = Path("src/tokenops_cost_auditor/web/templates/app/_sprite.html").read_text()
        source = Path("design/icons.svg").read_text()
        for symbol in re.findall(r'<symbol id="([^"]+)"', source):
            assert f'id="{symbol}"' in sprite

    def test_no_cdn_references_in_templates(self) -> None:
        for path in Path("src/tokenops_cost_auditor/web/templates").rglob("*.html"):
            text = path.read_text()
            assert "https://cdn" not in text and "unpkg.com" not in text, path
