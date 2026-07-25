"""Whole-surface EXPERIENCE gate (founder 2026-07-25: "why are these reaching prod?").

Per-slice diff gates verify a slice against its spec on curated fixtures. They cannot
see the EMERGENT, CUMULATIVE, real-data issues that actually reached prod — a cluttered
findings list, a figure page that forgot the honesty banner, a connect CTA rendered
twice. This gate renders the KEY authenticated surfaces with a REAL audit and asserts
those lived-quality invariants, so each such issue becomes a permanent regression test.

It is deliberately CROSS-CUTTING: it does not care which slice touched a page — only that
the whole surface reads right.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, User

FIXTURES = Path(__file__).parent / "fixtures"
EMAIL = "walkthrough@example.com"
HDR = {"X-User-Email": EMAIL}

# The prominent honesty banner the shell renders when a past audit exists but nothing
# is connected — the figures are HISTORY and must say so on EVERY page that shows them.
BANNER = "Nothing is connected to bring in new usage"
# Every page that renders LAST-AUDIT FIGURES. A new figure page added without the banner
# is the /breakdown-class bug — this list is the cross-cutting contract.
FIGURE_PAGES = ("/dashboard", "/findings", "/breakdown", "/runs", "/explore")


def _seed_done_audit(app: FastAPI) -> str:
    """A completed audit from an UPLOAD — so nothing is connected (no source/key/device):
    the figures are historical and the honesty banner must show."""
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == EMAIL)) or User(email=EMAIL)
        session.add(user)
        session.flush()
        audit = Audit(user_id=user.id, status="queued")
        session.add(audit)
        session.flush()
        upload_dir = Path(app.state.settings.upload_dir) / audit.id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / "original.jsonl"
        shutil.copyfile(FIXTURES / "waste_pack_anthropic.jsonl", dest)
        audit.upload_path = str(dest)
        session.commit()
        audit_id = audit.id
    app.state.runner.run(audit_id)
    return audit_id


class TestExperienceWalkthrough:
    def test_honesty_banner_on_every_figure_page(self, app: FastAPI, settings: Settings) -> None:
        # a past audit + nothing connected → EVERY page showing those figures must carry
        # the honesty banner, not a hand-maintained list a new page can silently miss.
        _seed_done_audit(app)
        client = TestClient(app)
        for path in FIGURE_PAGES:
            resp = client.get(path, headers=HDR)
            assert resp.status_code == 200, path
            assert BANNER in resp.text, (
                f"{path} shows last-audit figures WITHOUT the honesty banner"
            )

    def test_findings_page_is_clean_and_distinct(self, app: FastAPI, settings: Settings) -> None:
        _seed_done_audit(app)
        page = TestClient(app).get("/findings", headers=HDR).text
        assert "$0.00" not in page  # no zero-value savings clutter
        assert "on <code>" in page  # findings name their route → read as distinct

    def test_sources_page_shows_each_connect_cta_once(
        self, app: FastAPI, settings: Settings
    ) -> None:
        # nothing connected: the connect CTA must appear ONCE, not duplicated across the
        # top add-bar AND the empty state (the "mangled Sources page" bug).
        _seed_done_audit(app)
        page = TestClient(app).get("/sources", headers=HDR).text
        assert page.count("Connect OpenAI") == 1, "Connect OpenAI CTA is duplicated on /sources"
        assert page.count("Connect Anthropic") == 1, (
            "Connect Anthropic CTA is duplicated on /sources"
        )
