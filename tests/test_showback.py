"""Showback CSV export (FR-38, LLD §9.5, O-2) — the finance-grade allocation
file a workspace owner downloads from /breakdown/showback.csv, byte-identical
to the tokenomics.json artifact the runner already wrote.

A: services/dashboard/showback.render_csv — pure serializer goldens, no app.
B: GET /breakdown/showback.csv — owner-only (MANAGE_BILLING) RBAC + honest 404s.
C: the /breakdown page's "Download showback CSV" affordance — owner-only,
   ABSENT (not merely hidden) for every other role and when there's no audit.
D: the whole journey — upload, run, click, download, byte-for-byte.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, User, WorkspaceMember
from tokenops_cost_auditor.persistence.repo import (
    get_or_create_user,
    get_or_create_workspace,
    set_active_workspace,
)
from tokenops_cost_auditor.services.dashboard import showback, tokenomics
from tokenops_cost_auditor.services.pricing.coster import apply
from tokenops_cost_auditor.services.pricing.table import PricingTable

pytestmark = [pytest.mark.verifies_requirement("FR-38")]

FIXTURES = Path(__file__).parent / "fixtures"
TABLE = PricingTable.load()

EMAIL = "showback-owner@example.com"
HDR = {"X-User-Email": EMAIL}
# every role the O-2 matrix denies Perm.MANAGE_BILLING (tests/test_authz.py pins
# this set structurally; showback re-proves it end-to-end over the real route).
NON_OWNER_ROLES = ("admin", "member", "viewer")


def _priced(rows: list[dict]) -> pd.DataFrame:
    """A minimal priced frame — copied from tests/test_tokenomics.py's helper
    (test files don't import each other's fixtures in this house)."""
    defaults = {
        "provider": "anthropic",
        "model": "claude-opus-4-8",
        "ts": datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "tag": "chat",
        "prefix_hash": "h" * 64,
        "endpoint": "",
        "request_id": "r",
    }
    frame = pd.DataFrame([{**defaults, **r} for r in rows])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    priced, _ = apply(TABLE, frame)
    return priced


def _seed_audit(app: FastAPI, fixture: str, email: str = EMAIL) -> str:
    """A queued audit for `email`, its upload file staged on disk — the same
    seed idiom as tests/test_breakdown.py::_seed_audit (run it with
    app.state.runner.run(audit_id) to get a real DONE audit + tokenomics.json)."""
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == email)) or User(email=email)
        session.add(user)
        session.flush()
        audit = Audit(user_id=user.id, status="queued")
        session.add(audit)
        session.flush()
        upload_dir = Path(app.state.settings.upload_dir) / audit.id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"original{Path(fixture).suffix}"
        shutil.copyfile(FIXTURES / fixture, dest)
        audit.upload_path = str(dest)
        session.commit()
        return audit.id


def _seed_coarse_audit(app: FastAPI, email: str = EMAIL) -> str:
    """A DONE audit from a connected source (source_id set) with NO
    tokenomics.json on disk — mirrors tests/test_breakdown.py::_seed_coarse_audit."""
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == email)) or User(email=email)
        session.add(user)
        session.flush()
        audit = Audit(user_id=user.id, status="done", source_id="src_connected_1")
        session.add(audit)
        session.commit()
        return audit.id


def _seed_non_owner_members(app: FastAPI) -> None:
    """One member per non-owner role, sharing EMAIL's workspace (mirrors
    tests/test_rbac_journey.py::_seed) — for the RBAC + affordance probes."""
    with app.state.session_factory() as s:
        owner = get_or_create_user(s, EMAIL)
        ws = get_or_create_workspace(s, owner)
        for role in NON_OWNER_ROLES:
            u = get_or_create_user(s, f"showback-{role}@example.com")
            s.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role=role))
            s.flush()
            set_active_workspace(s, u.id, ws.id)
        s.commit()


class TestRenderCsvGoldens:
    """FR-38 / LLD §9.5: services/dashboard/showback.render_csv is a pure
    serializer over an already-built artifact dict — no app needed."""

    def test_fixed_artifact_pins_the_exact_csv_bytes(self) -> None:
        """Hand-written artifact -> the ENTIRE CSV string, \\r\\n included. The
        float values are shared Python variables (real fp noise, long reprs)
        so the expected string can't silently drift from str()'s own output —
        what's actually being pinned is the STRUCTURE: header, dimension order,
        column order, and the caveat riding every row."""
        share_opus = 0.1 + 0.2  # 0.30000000000000004 — classic fp noise
        share_luna = 1.0 - share_opus  # 0.6999999999999997
        monthly_opus = 1234.5000000000002
        monthly_untagged = 422.40000000000003
        artifact = {
            "pct_attributed": 0.833,
            "by_model": [
                {
                    "name": "claude-opus-4-8",
                    "calls": 42,
                    "monthly_usd": monthly_opus,
                    "share": share_opus,
                },
                {
                    "name": "gpt-5.6-luna",
                    "calls": 7,
                    "monthly_usd": 88.4,
                    "share": share_luna,
                },
            ],
            "by_route": [
                {"name": "chat", "calls": 30, "monthly_usd": 900.1, "share": 0.75},
                {
                    "name": "(untagged)",
                    "calls": 19,
                    "monthly_usd": monthly_untagged,
                    "share": 0.25,
                },
            ],
        }
        caveat = "83% of spend carries a route tag"  # 0.833 * 100 -> :.0f -> 83
        expected = (
            "dimension,name,calls,monthly_usd,share,pct_attributed_caveat\r\n"
            f"model,claude-opus-4-8,42,{monthly_opus},{share_opus},{caveat}\r\n"
            f"model,gpt-5.6-luna,7,88.4,{share_luna},{caveat}\r\n"
            f"route,chat,30,900.1,0.75,{caveat}\r\n"
            f"route,(untagged),19,{monthly_untagged},0.25,{caveat}\r\n"
        )
        assert showback.render_csv(artifact) == expected

    def test_empty_allocation_is_header_plus_comment_only(self) -> None:
        expected = (
            "dimension,name,calls,monthly_usd,share,pct_attributed_caveat\r\n"
            "# nothing to allocate — none of this audit's requests could be priced\r\n"
        )
        for artifact in (
            {},
            {"by_model": [], "by_route": []},
            {"by_model": None, "by_route": None, "pct_attributed": 0.0},
        ):
            assert showback.render_csv(artifact) == expected

    def test_caveat_rides_every_row_fixed_template(self) -> None:
        artifact = {
            "pct_attributed": 0.6667,
            "by_model": [{"name": "m1", "calls": 1, "monthly_usd": 10.0, "share": 1.0}],
            "by_route": [
                {"name": "r1", "calls": 1, "monthly_usd": 5.0, "share": 0.5},
                {"name": "r2", "calls": 1, "monthly_usd": 5.0, "share": 0.5},
            ],
        }
        rows = list(csv.reader(io.StringIO(showback.render_csv(artifact))))[1:]
        expected_caveat = "67% of spend carries a route tag"  # 66.67 -> :.0f -> 67
        assert len(rows) == 3
        assert all(row[-1] == expected_caveat for row in rows)

    def test_model_rows_before_route_rows_artifact_order_preserved(self) -> None:
        # deliberately NOT sorted by monthly $ desc — render_csv must not re-rank
        artifact = {
            "pct_attributed": 1.0,
            "by_model": [
                {"name": "cheap-model", "calls": 1, "monthly_usd": 1.0, "share": 0.1},
                {"name": "pricey-model", "calls": 1, "monthly_usd": 90.0, "share": 0.9},
            ],
            "by_route": [
                {"name": "z-route", "calls": 1, "monthly_usd": 50.0, "share": 0.5},
                {"name": "a-route", "calls": 1, "monthly_usd": 50.0, "share": 0.5},
            ],
        }
        rows = list(csv.reader(io.StringIO(showback.render_csv(artifact))))[1:]
        assert [(r[0], r[1]) for r in rows] == [
            ("model", "cheap-model"),
            ("model", "pricey-model"),
            ("route", "z-route"),
            ("route", "a-route"),
        ]

    def test_slice_name_with_comma_and_quote_round_trips(self) -> None:
        tricky_name = 'Ops, "prod" tier'
        artifact = {
            "pct_attributed": 1.0,
            "by_model": [],
            "by_route": [{"name": tricky_name, "calls": 3, "monthly_usd": 12.0, "share": 1.0}],
        }
        rows = list(csv.reader(io.StringIO(showback.render_csv(artifact))))
        assert rows[1][1] == tricky_name


class TestRenderCsvByteVerbatimProperty:
    """FR-38 Accept: the CSV must reconcile to the tokenomics goldens EXACTLY —
    figures are the artifact's own json.dumps bytes, never recomputed/re-rounded."""

    def test_every_dollar_and_share_field_round_trips_through_json_unchanged(self) -> None:
        frame = _priced(
            [
                {
                    "model": "claude-opus-4-8",
                    "tag": "chat",
                    "prompt_tokens": 5000,
                    "cached_tokens": 137,
                },
                {
                    "model": "gpt-5.6-luna",
                    "provider": "openai",
                    "tag": "b",
                    "prompt_tokens": 733,
                    "completion_tokens": 91,
                },
                {"tag": "", "prompt_tokens": 233},
            ]
        )
        tk = tokenomics.compute(frame)
        # exactly what the runner writes to disk: dataclasses.asdict -> json.dumps
        # -> (later) json.loads by the loader/route.
        artifact = json.loads(json.dumps(dataclasses.asdict(tk)))
        csv_text = showback.render_csv(artifact)

        reader = csv.reader(io.StringIO(csv_text))
        assert next(reader) == list(showback.HEADER)
        rows = list(reader)
        # 2 model slices (opus combines rows 1+3) + 3 route slices (chat/b/untagged)
        assert len(rows) == 5
        for row in rows:
            monthly_usd_field, share_field = row[3], row[4]
            assert json.dumps(json.loads(monthly_usd_field)) == monthly_usd_field
            assert json.dumps(json.loads(share_field)) == share_field
        assert {r[1] for r in rows if r[0] == "route"} == {"chat", "b", tokenomics.UNTAGGED}


class TestShowbackRouteHappyPath:
    """GET /breakdown/showback.csv, owner with a real DONE audit."""

    def test_owner_downloads_200_csv_with_attachment_headers(self, app: FastAPI) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)

        resp = TestClient(app).get("/breakdown/showback.csv", headers=HDR)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        assert (
            resp.headers["content-disposition"]
            == f'attachment; filename="showback-{audit_id[:8]}.csv"'
        )
        assert resp.text.startswith(
            "dimension,name,calls,monthly_usd,share,pct_attributed_caveat\r\n"
        )

    def test_downloaded_body_is_byte_identical_to_the_artifact_on_disk(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        artifact = json.loads(
            (Path(settings.report_dir) / audit_id / "tokenomics.json").read_text(encoding="utf-8")
        )

        resp = TestClient(app).get("/breakdown/showback.csv", headers=HDR)
        rows = list(csv.reader(io.StringIO(resp.text)))[1:]
        by_key = {(r[0], r[1]): r for r in rows}
        for dimension, key in (("model", "by_model"), ("route", "by_route")):
            for s in artifact[key]:
                row = by_key[(dimension, s["name"])]
                assert row[2] == str(s["calls"])
                assert row[3] == str(s["monthly_usd"])  # byte-identical string form
                assert row[4] == str(s["share"])


class TestShowbackRouteRbac:
    """O-2: only the workspace owner (Perm.MANAGE_BILLING) may download the
    showback CSV — every other role fails closed with 403."""

    def test_non_owner_roles_get_403(self, app: FastAPI) -> None:
        _seed_non_owner_members(app)
        client = TestClient(app)
        for role in NON_OWNER_ROLES:
            resp = client.get(
                "/breakdown/showback.csv", headers={"X-User-Email": f"showback-{role}@example.com"}
            )
            assert resp.status_code == 403, role


class TestShowbackRouteNotFound:
    """No audit, or an audit with no tokenomics artifact, is an honest 404 —
    never an empty 200 accounting could mistake for a real (zero) export."""

    def test_owner_no_audit_404(self, app: FastAPI) -> None:
        resp = TestClient(app).get("/breakdown/showback.csv", headers=HDR)
        assert resp.status_code == 404

    def test_owner_coarse_source_audit_no_artifact_404(self, app: FastAPI) -> None:
        _seed_coarse_audit(app)
        resp = TestClient(app).get("/breakdown/showback.csv", headers=HDR)
        assert resp.status_code == 404

    def test_owner_artifact_purged_after_a_real_run_404(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        (Path(settings.report_dir) / audit_id / "tokenomics.json").unlink()

        resp = TestClient(app).get("/breakdown/showback.csv", headers=HDR)
        assert resp.status_code == 404


class TestShowbackFr22Privacy:
    """FR-22: no prompt/completion free text may ever leak into a response —
    mirrors the marker-absence tripwire in
    tests/test_developer_platform.py::test_fr22_shape_counts_and_dollars_only."""

    def test_csv_body_has_no_prompt_completion_content_markers(self, app: FastAPI) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)

        resp = TestClient(app).get("/breakdown/showback.csv", headers=HDR)
        assert resp.status_code == 200
        blob = resp.text.lower()
        assert "prompt" not in blob and "completion" not in blob and "content" not in blob


class TestShowbackAffordanceVisibility:
    """The /breakdown "Download showback CSV" button + its caption — owner-only,
    ABSENT (not merely hidden) for every other role and with no audit yet
    (O-2 absence idiom, same as the Billing nav)."""

    def test_owner_sees_button_and_caption_non_billing_role_sees_neither(
        self, app: FastAPI
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        _seed_non_owner_members(app)

        owner_page = TestClient(app).get("/breakdown", headers=HDR).text
        assert "Download showback CSV" in owner_page
        assert 'href="/breakdown/showback.csv"' in owner_page
        assert "Showback = the allocation file accounting uses" in owner_page

        for role in NON_OWNER_ROLES:
            page = (
                TestClient(app)
                .get("/breakdown", headers={"X-User-Email": f"showback-{role}@example.com"})
                .text
            )
            assert "Download showback CSV" not in page
            assert 'href="/breakdown/showback.csv"' not in page
            assert "Showback = the allocation file accounting uses" not in page

    def test_no_audit_state_the_whole_widget_is_absent(self, app: FastAPI) -> None:
        page = TestClient(app).get("/breakdown", headers=HDR).text
        assert "No breakdown yet" in page  # the honest empty state (test_breakdown.py)
        assert "Download showback CSV" not in page
        assert 'href="/breakdown/showback.csv"' not in page
        assert "By route (cost allocation)" not in page  # the whole section, not just the button


class TestShowbackJourney:
    """R-VERTICAL, ship=walk: the whole path a workspace owner walks — upload
    a log, the audit runs, /breakdown shows the button, download the CSV,
    figures agree with the on-disk artifact byte-for-byte."""

    def test_owner_uploads_runs_downloads_and_figures_match_the_artifact(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)

        page = TestClient(app).get("/breakdown", headers=HDR)
        assert page.status_code == 200
        assert "Download showback CSV" in page.text
        assert 'href="/breakdown/showback.csv"' in page.text

        resp = TestClient(app).get("/breakdown/showback.csv", headers=HDR)
        assert resp.status_code == 200

        artifact = json.loads(
            (Path(settings.report_dir) / audit_id / "tokenomics.json").read_text(encoding="utf-8")
        )
        rows = list(csv.reader(io.StringIO(resp.text)))[1:]
        by_key = {(r[0], r[1]): r for r in rows}
        for dimension, key in (("model", "by_model"), ("route", "by_route")):
            for s in artifact[key]:
                row = by_key[(dimension, s["name"])]
                assert row[2] == str(s["calls"])
                assert row[3] == str(s["monthly_usd"])
                assert row[4] == str(s["share"])
