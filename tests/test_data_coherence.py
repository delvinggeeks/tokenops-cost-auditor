"""Data coherence & honest freshness (founder 2026-07-24 walkthrough).

The bug the founder saw on prod: the Sources page shows "nothing connected" while
Overview/Findings keep rendering the last audit's real numbers with NO signal that
they are HISTORY — so old figures read as live/stale. These tests pin the fix:
when a past audit exists but nothing is currently connected, the pages that render
last-audit FIGURES carry the "nothing connected — figures are from your last audit"
banner, and the terse "· nothing connected" topbar freshness marker is honest on
EVERY app page; a workspace with a live feed shows neither; a brand-new workspace
with no audit shows the honest "no data yet".
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import Audit, Device, IngestKey, Source, utcnow
from tokenops_cost_auditor.persistence.repo import (
    create_audit,
    get_or_create_user,
    get_or_create_workspace,
)

USER = "coherence-user@example.com"
BANNER = "Nothing is connected to bring in new usage"


def _seed(app: FastAPI, *, with_source: bool, with_audit: bool = True) -> None:
    """USER owns a workspace; optionally a live source and a completed audit."""
    with app.state.session_factory() as s:
        user = get_or_create_user(s, USER)
        ws = get_or_create_workspace(s, user)
        if with_source:
            s.add(
                Source(
                    user_id=user.id,
                    workspace_id=ws.id,
                    provider="openai",
                    label="OpenAI prod",
                    status="active",
                )
            )
        if with_audit:
            audit = create_audit(s, user.id)
            audit.status = "done"
            audit.report_ready_at = utcnow()
        s.commit()


def _revoke_all_sources(app: FastAPI) -> None:
    with app.state.session_factory() as s:
        for src in s.scalars(select(Source)).all():
            src.status = "revoked"
            src.revoked_at = utcnow()
        s.commit()


class TestDataCoherence:
    def test_healthy_workspace_shows_no_banner_and_live_freshness(self, app: FastAPI) -> None:
        _seed(app, with_source=True)
        for path in ("/dashboard", "/sources", "/runs"):
            page = TestClient(app).get(path, headers={"X-User-Email": USER}).text
            assert BANNER not in page, path
            assert "Data as of" in page and "nothing connected" not in page, path

    def test_disconnected_shows_banner_on_figure_pages_marker_everywhere(
        self, app: FastAPI
    ) -> None:
        # the founder's exact case: a done audit, then all sources revoked. The
        # data persists. The banner shows on pages that render last-audit FIGURES
        # (both _shell_ctx pages /dashboard /runs /statements); the terse
        # "· nothing connected" topbar marker is honest EVERYWHERE, but account /
        # own-subject pages carry NO banner (ux O-COH f.4 — no numbers there to
        # contextualize; /sources is its own subject).
        _seed(app, with_source=True)
        _revoke_all_sources(app)
        c = TestClient(app)
        for path in ("/dashboard", "/runs", "/statements"):
            page = c.get(path, headers={"X-User-Email": USER}).text
            assert BANNER in page, path
            assert "nothing connected" in page, path
        for path in ("/settings", "/sources"):
            page = c.get(path, headers={"X-User-Email": USER}).text
            assert BANNER not in page, path  # no banner off the figure pages
            assert "nothing connected" in page, path  # topbar marker honest everywhere

    def test_audit_progress_page_carries_the_freshness_marker(self, app: FastAPI) -> None:
        # the audit-progress theater is a shell page that bypasses _shell_ctx — it
        # must still carry the freshness marker (system-tester O-COH gap), or it
        # silently disagrees with every other page. Banner stays OFF (single-audit
        # view, page="upload", not a figures page).
        _seed(app, with_source=True)
        _revoke_all_sources(app)
        with app.state.session_factory() as s:
            audit_id = s.scalar(select(Audit.id))
        page = (
            TestClient(app).get(f"/audits/{audit_id}/progress", headers={"X-User-Email": USER}).text
        )
        assert "nothing connected" in page  # freshness marker present (was missing)
        assert BANNER not in page  # not a figures page → no banner

    def test_a_live_device_counts_as_connected(self, app: FastAPI) -> None:
        # a linked machine (unrevoked Device) is a live feed too — the OR-arm cold
        # O-COH f.1 flagged as untested. No banner.
        _seed(app, with_source=False)  # audit exists, no source
        with app.state.session_factory() as s:
            user = get_or_create_user(s, USER)
            ws = get_or_create_workspace(s, user)
            s.add(
                Device(user_id=user.id, workspace_id=ws.id, hostname="mac-01", consent_at=utcnow())
            )
            s.commit()
        page = TestClient(app).get("/dashboard", headers={"X-User-Email": USER}).text
        assert BANNER not in page

    def test_brand_new_workspace_no_audit_no_banner(self, app: FastAPI) -> None:
        _seed(app, with_source=False, with_audit=False)
        page = TestClient(app).get("/dashboard", headers={"X-User-Email": USER}).text
        assert BANNER not in page
        assert "No data yet" in page  # honest zero-state, not a stale banner

    def test_a_live_ingest_key_counts_as_connected(self, app: FastAPI) -> None:
        # no active source, but an unrevoked ingest key means usage can still
        # arrive (SDK) — so the workspace is NOT disconnected and shows no banner.
        _seed(app, with_source=False)  # audit exists, no source
        with app.state.session_factory() as s:
            user = get_or_create_user(s, USER)
            ws = get_or_create_workspace(s, user)
            s.add(IngestKey(user_id=user.id, workspace_id=ws.id, label="sdk", key_hash="hash-coh"))
            s.commit()
        page = TestClient(app).get("/dashboard", headers={"X-User-Email": USER}).text
        assert BANNER not in page
