"""T-F2 · FR-35 — cohort export + consent: the factory's ONLY inlet.

A: services/flywheel/export.build — the envelope builder (golden fixture,
   below-floor honesty, determinism, schema self-audit).
B: Settings — the workspace consent toggle (owner-only, audit-logged,
   non-owner absence + forged-POST 403).
C: /admin — the cohort-export row + GET /admin/cohort-export.json (token
   gate, FR-22 marker-absence, honest below-floor reason).
D: the engine boundary — services/rules and services/pricing never learn
   the word "cohort" (T-NFR-01 spirit, HLD §8.2).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.persistence.models import (
    Audit,
    AuditLogEntry,
    FindingRow,
    User,
    WorkspaceMember,
)
from tokenops_cost_auditor.persistence.repo import get_or_create_workspace, set_active_workspace
from tokenops_cost_auditor.services.flywheel import export

PERIOD = "2026-07"
WHEN = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
OWNER_EMAIL = "coh-owner@example.com"
HDR = {"X-User-Email": OWNER_EMAIL}
NON_OWNER_ROLES = ("admin", "member", "viewer")


def _artifact(monthly_spend_usd: float = 100.0, shapes: list[dict[str, str]] | None = None) -> dict:
    return {
        "monthly_spend_usd": monthly_spend_usd,
        "tokens_in": 1000,
        "tokens_out": 200,
        "tokens_cached": 50,
        "cache_hit_rate": 0.05,
        "out_in_ratio": 0.2,
        "by_model": [],
        "by_route": [],
        "pct_priced": 1.0,
        "pct_attributed": 1.0,
        "shapes": {"schema": 1, "by_route": shapes if shapes is not None else []},
    }


def seed_workspace(
    app: FastAPI,
    email: str,
    *,
    opt_in: bool = True,
    findings: tuple[str, ...] = ("d2_missing_cache",),
    write_artifact: bool = True,
    monthly_spend_usd: float = 100.0,
    shapes: list[dict[str, str]] | None = None,
    when: datetime = WHEN,
) -> tuple[str, str]:
    """A workspace-of-one with one DONE audit `when`, optionally opted into the
    cohort export, with N findings and a tokenomics.json artifact on disk
    (mirrors what services/runner.py actually writes). Returns (workspace_id,
    audit_id)."""
    with app.state.session_factory() as session:
        user = User(email=email)
        session.add(user)
        session.flush()
        workspace = get_or_create_workspace(session, user)
        workspace.cohort_opt_in = opt_in
        audit = Audit(
            user_id=user.id,
            workspace_id=workspace.id,
            status="done",
            total_spend_usd=monthly_spend_usd,
            created_at=when,
            report_ready_at=when,
        )
        session.add(audit)
        session.flush()
        for i, detector in enumerate(findings):
            session.add(
                FindingRow(
                    audit_id=audit.id,
                    finding_id=f"F-{i:03d}",
                    detector=detector,
                    route="claude-sonnet-5",
                    severity="high",
                    monthly_impact_usd=10.0,
                    confidence="estimated",
                    fix_text="fix it",
                    evidence_sample=[{"row_idx": 1, "tokens": 10}],
                )
            )
        session.commit()
        workspace_id, audit_id = workspace.id, audit.id
    if write_artifact:
        report_dir = Path(app.state.settings.report_dir) / audit_id
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "tokenomics.json").write_text(
            json.dumps(_artifact(monthly_spend_usd, shapes)), encoding="utf-8"
        )
    return workspace_id, audit_id


def _seed_floor_cohort(app: FastAPI, n: int = 10) -> list[str]:
    """n opted-in workspaces, each with one done audit + artifact in PERIOD."""
    return [seed_workspace(app, f"member{i}@example.com")[0] for i in range(n)]


class TestBuilderGolden:
    def test_envelope_pins_the_exact_shape_and_values(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 9)
        ws_id, _ = seed_workspace(
            app,
            OWNER_EMAIL,
            findings=("d2_missing_cache", "d2_missing_cache", "d6_chatty_loop"),
            monthly_spend_usd=250.5,
            shapes=[
                {"route": "a", "shape": "AGENT_LOOP", "rationale": "r"},
                {"route": "b", "shape": "AGENT_LOOP", "rationale": "r"},
                {"route": "c", "shape": "STEADY", "rationale": "r"},
            ],
        )
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        assert result.k == 10 and result.floor == 10 and result.reason == ""
        assert len(result.envelopes) == 10
        mine = next(
            e
            for e in result.envelopes
            if e.workspace_ref == export.workspace_pseudonym(app.state.settings.secret_key, ws_id)
        )
        assert mine.schema_version == "1.0"
        assert mine.period == PERIOD
        assert mine.k == 10
        assert mine.features["monthly_spend_usd"] == 250.5
        assert mine.features["tokens_in"] == 1000
        assert mine.features["tokens_out"] == 200
        assert mine.features["tokens_cached"] == 50
        assert mine.features["cache_hit_rate"] == 0.05
        assert mine.features["out_in_ratio"] == 0.2
        assert mine.features["detector_fire_rates"]["d2"] == 1.0  # fired on its 1 audit
        assert mine.features["detector_fire_rates"]["d6"] == 1.0
        assert mine.features["detector_fire_rates"]["d1"] == 0.0
        assert set(mine.features["detector_fire_rates"]) == set(export.DETECTOR_IDS)
        assert mine.features["shape_mix"]["AGENT_LOOP"] == round(2 / 3, 4)
        assert mine.features["shape_mix"]["STEADY"] == round(1 / 3, 4)
        assert set(mine.features["shape_mix"]) == set(export.SHAPE_KEYS)

    def test_workspace_ref_is_opaque_keyed_and_never_the_id(self, app: FastAPI) -> None:
        ws_id, _ = seed_workspace(app, OWNER_EMAIL)
        ref = export.workspace_pseudonym(app.state.settings.secret_key, ws_id)
        assert ref != ws_id
        assert ws_id not in ref
        assert ref == export.workspace_pseudonym(app.state.settings.secret_key, ws_id)  # stable
        other_secret = "a-different-secret-0000000000000000000000000000"
        assert ref != export.workspace_pseudonym(other_secret, ws_id)

    def test_workspace_and_user_pseudonym_spaces_never_collide(self, app: FastAPI) -> None:
        """The DISTINCT HKDF info context (issue requirement): the same raw id
        string run through both derivations must never coincide."""
        from tokenops_cost_auditor.services.flywheel import frame

        secret = app.state.settings.secret_key
        shared_id = "abc123abc123abc123abc123abc1234"
        assert export.workspace_pseudonym(secret, shared_id) != frame.cohort_pseudonym(
            secret, shared_id
        )

    def test_no_recompute_drift_missing_artifact_falls_back_honestly(self, app: FastAPI) -> None:
        """A coarse-source/purged audit has no tokenomics.json — vitals fall back
        to the audited total_spend_usd and honest zeros, never a crash."""
        _seed_floor_cohort(app, 9)
        ws_id, _ = seed_workspace(app, OWNER_EMAIL, write_artifact=False, monthly_spend_usd=42.0)
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        mine = next(
            e
            for e in result.envelopes
            if e.workspace_ref == export.workspace_pseudonym(app.state.settings.secret_key, ws_id)
        )
        assert mine.features["monthly_spend_usd"] == 42.0
        assert mine.features["tokens_in"] == 0
        assert mine.features["cache_hit_rate"] == 0.0
        assert mine.features["shape_mix"] == dict.fromkeys(export.SHAPE_KEYS, 0.0)


class TestBelowFloorHonesty:
    def test_nine_opted_in_workspaces_export_nothing_and_say_why(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 9)
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        assert result.envelopes == ()
        assert result.k == 9 and result.floor == 10
        assert "9" in result.reason and "10" in result.reason
        assert "re-identification" in result.reason  # names WHY, not just a number

    def test_tenth_workspace_crosses_the_floor_exactly(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 9)
        seed_workspace(app, "tenth@example.com")
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        assert result.k == 10 and len(result.envelopes) == 10 and result.reason == ""

    def test_non_opted_in_workspaces_never_count_toward_k(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 9)
        seed_workspace(app, "excluded@example.com", opt_in=False)
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        assert result.k == 9  # the opted-out workspace does not push it to 10
        assert result.envelopes == ()

    def test_audits_outside_the_period_do_not_count(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 9)
        other_month = datetime(2026, 6, 15, tzinfo=UTC)
        seed_workspace(app, "wrongmonth@example.com", when=other_month)
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        assert result.k == 9


class TestDeterminism:
    def test_two_builds_of_the_same_state_are_byte_identical(self, app: FastAPI) -> None:
        import dataclasses

        _seed_floor_cohort(app, 12)
        with app.state.session_factory() as session:
            one = export.build(session, app.state.settings, PERIOD)
            two = export.build(session, app.state.settings, PERIOD)

        def as_json(r: export.ExportResult) -> str:
            return json.dumps([dataclasses.asdict(e) for e in r.envelopes], sort_keys=True)

        assert as_json(one) == as_json(two)
        assert one.envelopes == two.envelopes


class TestSchemaSelfAudit:
    def test_a_real_envelope_has_no_violations(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 10)
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        for envelope in result.envelopes:
            assert export.envelope_violations(envelope) == []

    def test_a_free_text_field_is_caught(self, app: FastAPI) -> None:
        import dataclasses

        _seed_floor_cohort(app, 10)
        with app.state.session_factory() as session:
            result = export.build(session, app.state.settings, PERIOD)
        tampered = dataclasses.replace(
            result.envelopes[0],
            features={**result.envelopes[0].features, "prompt_text": "leaked!"},
        )
        problems = export.envelope_violations(tampered)
        assert problems and "feature keys" in problems[0]

    def test_feature_keys_match_the_lld_contract(self) -> None:
        expected = {
            "monthly_spend_usd",
            "tokens_in",
            "tokens_out",
            "tokens_cached",
            "cache_hit_rate",
            "out_in_ratio",
            "detector_fire_rates",
            "shape_mix",
        }
        assert expected == export.FEATURE_KEYS


class TestConsentJourney:
    def _seed_members(self, app: FastAPI) -> None:
        with app.state.session_factory() as s:
            owner = s.execute(select(User).where(User.email == OWNER_EMAIL)).scalar_one()
            ws = get_or_create_workspace(s, owner)
            for role in NON_OWNER_ROLES:
                u = User(email=f"coh-{role}@example.com")
                s.add(u)
                s.flush()
                s.add(WorkspaceMember(workspace_id=ws.id, user_id=u.id, role=role))
                s.flush()
                set_active_workspace(s, u.id, ws.id)
            s.commit()

    def test_default_off_opt_in_present_opt_out_absent_again(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 9)
        ws_id, _ = seed_workspace(app, OWNER_EMAIL, opt_in=False)
        ref = export.workspace_pseudonym(app.state.settings.secret_key, ws_id)

        with app.state.session_factory() as session:
            default_off = export.build(session, app.state.settings, PERIOD)
        assert ref not in {e.workspace_ref for e in default_off.envelopes}

        client = TestClient(app)
        r = client.post(
            "/settings/workspace/cohort-opt-in",
            headers=HDR,
            data={"cohort_opt_in": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        with app.state.session_factory() as session:
            opted_in = export.build(session, app.state.settings, PERIOD)
        assert ref in {e.workspace_ref for e in opted_in.envelopes}

        r = client.post(
            "/settings/workspace/cohort-opt-in",
            headers=HDR,
            data={},
            follow_redirects=False,
        )
        assert r.status_code == 303
        with app.state.session_factory() as session:
            opted_out_again = export.build(session, app.state.settings, PERIOD)
        assert ref not in {e.workspace_ref for e in opted_out_again.envelopes}

    def test_flip_is_audit_logged(self, app: FastAPI) -> None:
        seed_workspace(app, OWNER_EMAIL, opt_in=False)
        client = TestClient(app)
        client.post("/settings/workspace/cohort-opt-in", headers=HDR, data={"cohort_opt_in": "1"})
        with app.state.session_factory() as session:
            actions = [
                (e.action, e.subject) for e in session.execute(select(AuditLogEntry)).scalars()
            ]
        assert ("settings.cohort_opt_in", "opted_in") in actions

    def test_non_owner_sees_no_toggle_and_cannot_flip_it(self, app: FastAPI) -> None:
        seed_workspace(app, OWNER_EMAIL, opt_in=False)
        self._seed_members(app)
        client = TestClient(app)

        owner_page = client.get("/settings", headers=HDR).text
        assert "cohort_opt_in" in owner_page
        assert 'action="/settings/workspace/cohort-opt-in"' in owner_page

        for role in NON_OWNER_ROLES:
            hdr = {"X-User-Email": f"coh-{role}@example.com"}
            page = client.get("/settings", headers=hdr).text
            assert "cohort_opt_in" not in page
            assert 'action="/settings/workspace/cohort-opt-in"' not in page
            resp = client.post(
                "/settings/workspace/cohort-opt-in", headers=hdr, data={"cohort_opt_in": "1"}
            )
            assert resp.status_code == 403, role


class TestAdminSurface:
    def _client(self, app: FastAPI) -> tuple[TestClient, dict[str, str]]:
        app.state.settings.admin_token = "test-admin-token"
        return TestClient(app), {"X-Admin-Token": "test-admin-token"}

    def test_gate_absent_without_the_token(self, app: FastAPI) -> None:
        app.state.settings.admin_token = "test-admin-token"
        resp = TestClient(app).get("/admin/cohort-export.json")
        assert resp.status_code == 404

    def test_live_export_over_the_route(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 10)
        client, hdr = self._client(app)
        resp = client.get(f"/admin/cohort-export.json?period={PERIOD}", headers=hdr)
        assert resp.status_code == 200
        body = resp.json()
        assert body["k"] == 10 and body["floor"] == 10 and body["reason"] == ""
        assert len(body["envelopes"]) == 10
        assert body["envelopes"][0]["schema_version"] == "1.0"

    def test_below_floor_returns_zero_envelopes_and_the_reason(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 3)
        client, hdr = self._client(app)
        resp = client.get(f"/admin/cohort-export.json?period={PERIOD}", headers=hdr)
        assert resp.status_code == 200
        body = resp.json()
        assert body["envelopes"] == [] and body["k"] == 3
        assert "3" in body["reason"] and "10" in body["reason"]

    def test_download_is_audit_logged(self, app: FastAPI) -> None:
        _seed_floor_cohort(app, 10)
        client, hdr = self._client(app)
        client.get(f"/admin/cohort-export.json?period={PERIOD}", headers=hdr)
        with app.state.session_factory() as session:
            actions = [e.action for e in session.execute(select(AuditLogEntry)).scalars()]
        assert "cohort_export.downloaded" in actions

    def test_admin_home_row_live_and_below_floor(self, app: FastAPI) -> None:
        client, hdr = self._client(app)
        page = client.get("/admin", headers=hdr)
        assert page.status_code == 200
        assert "Cohort export" in page.text
        # below floor with nothing seeded yet -> honest reason, no LIVE claim
        assert "LIVE" not in page.text


class TestFr22MarkerAbsence:
    def test_export_response_carries_no_prompt_completion_content_markers(
        self, app: FastAPI
    ) -> None:
        _seed_floor_cohort(app, 10)
        app.state.settings.admin_token = "test-admin-token"
        resp = TestClient(app).get(
            f"/admin/cohort-export.json?period={PERIOD}",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        blob = resp.text.lower()
        assert "prompt" not in blob and "completion" not in blob and "content" not in blob


class TestEnginePurity:
    """T-NFR-01 posture (HLD §8.2): services/rules and services/pricing never
    learn the word 'cohort', and never import services/flywheel."""

    def test_rules_and_pricing_stay_cohort_blind(self) -> None:
        engine_pkgs = (
            "src/tokenops_cost_auditor/services/rules",
            "src/tokenops_cost_auditor/services/pricing",
        )
        for pkg in engine_pkgs:
            for mod in Path(pkg).glob("*.py"):
                text = mod.read_text()
                assert "cohort" not in text.lower(), mod
                assert "flywheel" not in text, mod

    def test_flywheel_package_still_imports_no_engine_or_network(self) -> None:
        """Re-proves T-FLY-07 with export.py in the package (test_flywheel.py's
        TestPackagePosture.test_09 covers this via the same glob, but the law
        is load-bearing enough for this slice to pin it here too)."""
        pkg = Path("src/tokenops_cost_auditor/services/flywheel")
        banned = re.compile(
            r"^\s*(from|import)\s+(requests|httpx|urllib|openai|anthropic|sklearn|"
            r"tokenops_cost_auditor\.services\.(rules|pricing|connectors))",
            re.M,
        )
        for mod in pkg.glob("*.py"):
            hit = banned.search(mod.read_text())
            assert hit is None, f"{mod.name}: {hit.group(0)!r}"


class TestMoneyMathUntouched:
    """Acceptance #4: no new money math — monthly_spend_usd is a passthrough of
    the audited artifact figure, never recomputed here."""

    def test_export_never_imports_pricing_coster(self) -> None:
        text = Path("src/tokenops_cost_auditor/services/flywheel/export.py").read_text()
        assert "import coster" not in text
        assert "from tokenops_cost_auditor.services.pricing" not in text
