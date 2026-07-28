"""T-F2 · FR-35 — cohort export + consent: services/flywheel/export.py's
CohortExportEnvelope v1, the /settings "Model improvement (cohort learning)"
card (owner-only opt-in), and GET /admin/cohort-export.json.

T-COH-01 envelope golden: one workspace's envelope pinned exactly, key order
          included (json.dumps of the dict, not just `==`).
T-COH-02 below the k-anonymity floor: no envelopes, an honest reason naming
          n and the floor.
T-COH-03 consent journey: opting a workspace in adds it to the cohort;
          opting back out removes it — k moves, membership moves.
T-COH-04 default-off: the card renders for a fresh owner, unchecked; checked
          after opt-in.
T-COH-05 RBAC: a non-owner member never sees the card and 403s on POST; the
          workspace flag is untouched.
T-COH-06 audit log: the flip is an AuditLogEntry, subject "opted in".
T-COH-07 admin route: below floor -> 404 naming the floor; live -> 200 with
          the schema, k, envelope count and a period-named download; the
          X-Admin-Token gate applies regardless of floor state.
T-COH-08 determinism: two build() calls over the same data serialize
          byte-for-byte identical.
T-COH-09 pseudonym spaces: workspace_ref is NOT frame's user pseudonym space,
          and no raw workspace id ever appears in the serialized export.
T-COH-10 FR-22 marker absence: seeded free-text markers (workspace name,
          artifact route/rationale) never survive into the serialized export.
T-COH-11 schema self-audit: export.schema_violations() == [].
T-COH-12 period discipline: an opted-in workspace's audit from a DIFFERENT
          period never enters this period's export.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    Audit,
    AuditLogEntry,
    CallAggregate,
    FindingRow,
    User,
    Workspace,
    WorkspaceMember,
    new_id,
)
from tokenops_cost_auditor.persistence.repo import (
    get_or_create_user,
    get_or_create_workspace,
    set_active_workspace,
)
from tokenops_cost_auditor.services.flywheel import export, frame

PERIOD = "2026-06"
PERIOD_DT = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
OTHER_PERIOD_DT = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
FLOOR = 10  # Settings.flywheel_l1_min_customers default (the `settings` fixture)


def _seed_workspace(
    session: Session, email: str, *, opt_in: bool, workspace_id: str | None = None
) -> tuple[str, str]:
    """Direct-build ONE user owning ONE workspace with an explicit consent flag.

    Ids are pre-assigned in Python (not left to the mapped_column default) so the
    owner WorkspaceMember row exists in the SAME flush as the User: conftest's
    fixture-parity `before_flush` hook auto-mints a workspace-of-one for any NEW
    User it sees with no owner membership yet, which would collide with (and
    IntegrityError against) the explicit membership this helper is about to add
    if the User were flushed alone first.
    """
    uid = new_id()
    wsid = workspace_id or new_id()
    session.add(User(id=uid, email=email))
    session.add(Workspace(id=wsid, name=f"ws-{email}"[:80], cohort_opt_in=opt_in))
    session.add(WorkspaceMember(workspace_id=wsid, user_id=uid, role="owner"))
    return uid, wsid


def _seed_done_audit(
    session: Session,
    user_id: str,
    workspace_id: str,
    *,
    when: datetime,
    total_spend_usd: float = 100.0,
) -> str:
    audit = Audit(
        user_id=user_id,
        workspace_id=workspace_id,
        status="done",
        report_ready_at=when,
        total_spend_usd=total_spend_usd,
    )
    session.add(audit)
    session.flush()
    return audit.id


def _seed_baseline_cohort(
    app: FastAPI,
    n: int = 10,
    *,
    when: datetime = PERIOD_DT,
    opt_in: bool = True,
    email_prefix: str = "cohort",
) -> list[tuple[str, str]]:
    """`n` opted-in workspaces, distinct owners, each with exactly ONE done audit
    in `when`'s period. Returns [(workspace_id, audit_id), ...]."""
    rows: list[tuple[str, str]] = []
    with app.state.session_factory() as session:
        for i in range(n):
            uid, wsid = _seed_workspace(session, f"{email_prefix}{i}@example.com", opt_in=opt_in)
            aid = _seed_done_audit(session, uid, wsid, when=when)
            rows.append((wsid, aid))
        session.commit()
    return rows


def _write_shapes_artifact(
    settings: Settings, audit_id: str, by_route: list[dict[str, str]]
) -> None:
    """The `shapes` block of report_dir/<audit_id>/tokenomics.json — what
    services/runner.py persists via services/dashboard/shapes.compute_shapes.
    export._features reads it back via tokenomics.load_artifact (only the
    `shapes.by_route` key is read, so a minimal artifact is a faithful stand-in)."""
    directory = Path(settings.report_dir) / audit_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "tokenomics.json").write_text(
        json.dumps({"shapes": {"schema": 1, "by_route": by_route}}), encoding="utf-8"
    )


class TestCohortExportEnvelopeGolden:
    """T-COH-01: one rich workspace's envelope, pinned exactly — ints, round-4
    ratios, all nine detector keys, all five shape keys, and the fixed key
    ORDER of Envelope.to_dict()/Features.to_dict() (json.dumps, not just ==)."""

    def test_envelope_matches_pinned_dict_and_key_order(
        self, app: FastAPI, settings: Settings
    ) -> None:
        target_id = "ws" + "0" * 30  # 32 chars — String(32), a fixed pseudonym input
        with app.state.session_factory() as session:
            uid, wsid = _seed_workspace(
                session, "target-owner@example.com", opt_in=True, workspace_id=target_id
            )
            audit_id = _seed_done_audit(session, uid, wsid, when=PERIOD_DT, total_spend_usd=500.0)
            session.add_all(
                [
                    CallAggregate(
                        audit_id=audit_id,
                        day=date(2026, 6, 1),
                        model="m1",
                        calls=10,
                        prompt_tokens=1000,
                        completion_tokens=200,
                        cached_tokens=250,
                        cost_usd=100.0,
                    ),
                    CallAggregate(
                        audit_id=audit_id,
                        day=date(2026, 6, 2),
                        model="m2",
                        calls=20,
                        prompt_tokens=3000,
                        completion_tokens=600,
                        cached_tokens=150,
                        cost_usd=400.0,
                    ),
                ]
            )
            session.add(
                FindingRow(
                    audit_id=audit_id,
                    finding_id="D2-000",
                    detector="d2_missing_cache",
                    route="m1",
                    severity="high",
                    monthly_impact_usd=50.0,
                    confidence="estimated",
                    fix_text="cache it",
                    evidence_sample=[{"row_idx": 1}],
                )
            )
            session.commit()

        _write_shapes_artifact(
            settings,
            audit_id,
            [
                {"route": "chat", "shape": "AGENT_LOOP", "rationale": "loop signal"},
                {"route": "images", "shape": "RETRY_BURST", "rationale": "burst signal"},
                {"route": "summarize", "shape": "STEADY", "rationale": "no signal crossed"},
                {"route": "embed", "shape": "STEADY", "rationale": "no signal crossed"},
            ],
        )
        # 9 more qualifying opted-in workspaces to clear the k=10 floor.
        _seed_baseline_cohort(app, n=9, when=PERIOD_DT, email_prefix="cohortother")

        with app.state.session_factory() as session:
            exp = export.build(session, settings, settings.secret_key, PERIOD)

        assert exp.live
        assert exp.k == 10
        assert len(exp.envelopes) == 10

        target_ref = export.workspace_ref(settings.secret_key, target_id)
        target_envelope = next(e for e in exp.envelopes if e.workspace_ref == target_ref)

        expected = {
            "schema_version": "1.0",
            "period": PERIOD,
            "workspace_ref": target_ref,
            "k": 10,
            "features": {
                "monthly_spend_usd": 500.0,
                "tokens_in": 4000,
                "tokens_out": 800,
                "tokens_cached": 400,
                "cache_hit_rate": 0.1,
                "out_in_ratio": 0.2,
                "detector_fire_rates": {
                    "d1": 0.0,
                    "d2": 1.0,  # the one FindingRow, on the workspace's one period audit
                    "d3": 0.0,
                    "d4": 0.0,
                    "d5": 0.0,
                    "d6": 0.0,
                    "d8": 0.0,
                    "d9": 0.0,
                    "d10": 0.0,
                },
                "shape_mix": {
                    "AGENT_LOOP": 0.25,
                    "RETRY_BURST": 0.25,
                    "CONTEXT_GROWTH": 0.0,
                    "UNCLAIMED_CACHE": 0.0,
                    "STEADY": 0.5,
                },
            },
        }
        golden = json.dumps(expected)
        assert json.dumps(target_envelope.to_dict()) == golden


class TestBelowKAnonymityFloor:
    """T-COH-02: 9 opted-in workspaces (one short of the 10 floor) -> honest
    refusal, no envelopes, no file."""

    def test_nine_opted_in_yields_no_envelopes_and_names_the_gap(
        self, app: FastAPI, settings: Settings
    ) -> None:
        _seed_baseline_cohort(app, n=9, when=PERIOD_DT, email_prefix="belowfloor")

        with app.state.session_factory() as session:
            exp = export.build(session, settings, settings.secret_key, PERIOD)

        assert exp.envelopes == ()
        assert exp.live is False
        assert "9" in exp.reason
        assert "10" in exp.reason
        assert "nothing is exported" in exp.reason


class TestConsentJourney:
    """T-COH-03: consent is the ONLY gate — k counts opted-in workspaces only,
    and flipping a workspace's flag moves it in and out of a live export."""

    def test_opt_in_enters_cohort_opt_out_leaves_it(self, app: FastAPI, settings: Settings) -> None:
        _seed_baseline_cohort(app, n=10, when=PERIOD_DT, email_prefix="qualifying")

        target_email = "opt-me-in@example.com"
        with app.state.session_factory() as session:
            uid, wsid = _seed_workspace(session, target_email, opt_in=False)
            _seed_done_audit(session, uid, wsid, when=PERIOD_DT)
            session.commit()
        target_ref = export.workspace_ref(settings.secret_key, wsid)

        # NOT opted in: absent, and doesn't count toward k, even with 10 others live.
        with app.state.session_factory() as session:
            exp = export.build(session, settings, settings.secret_key, PERIOD)
        assert exp.k == 10
        assert all(e.workspace_ref != target_ref for e in exp.envelopes)

        client = TestClient(app)
        hdr = {"X-User-Email": target_email}
        resp = client.post(
            "/settings/cohort", headers=hdr, data={"cohort_opt_in": "1"}, follow_redirects=False
        )
        assert resp.status_code == 303

        with app.state.session_factory() as session:
            exp2 = export.build(session, settings, settings.secret_key, PERIOD)
        assert exp2.k == 11
        assert any(e.workspace_ref == target_ref for e in exp2.envelopes)

        # opt-out: POST with the checkbox field absent (unchecked HTML checkboxes
        # submit nothing) flips it back off.
        resp2 = client.post("/settings/cohort", headers=hdr, data={}, follow_redirects=False)
        assert resp2.status_code == 303

        with app.state.session_factory() as session:
            exp3 = export.build(session, settings, settings.secret_key, PERIOD)
        assert exp3.k == 10
        assert all(e.workspace_ref != target_ref for e in exp3.envelopes)


class TestDefaultOffCardRendering:
    """T-COH-04: the card is present and unchecked for a fresh owner (default
    off), and reflects true state right after opt-in."""

    def test_fresh_owner_unchecked_then_checked_after_opt_in(self, app: FastAPI) -> None:
        client = TestClient(app)
        hdr = {"X-User-Email": "fresh-owner@example.com"}

        page = client.get("/settings", headers=hdr)
        assert page.status_code == 200
        assert "Model improvement (cohort learning)" in page.text
        checkbox = re.search(r'name="cohort_opt_in"[^>]*', page.text)
        assert checkbox is not None and "checked" not in checkbox.group(0)

        resp = client.post(
            "/settings/cohort", headers=hdr, data={"cohort_opt_in": "1"}, follow_redirects=False
        )
        assert resp.status_code == 303

        page2 = client.get("/settings", headers=hdr)
        checkbox2 = re.search(r'name="cohort_opt_in"[^>]*', page2.text)
        assert checkbox2 is not None and "checked" in checkbox2.group(0)


class TestRbacNonOwner:
    """T-COH-05: sharing data OUT of the workspace is an owner decision (O-2
    MANAGE_WORKSPACE) — a non-owner member sees no card and 403s on POST; the
    workspace flag is untouched by the attempt."""

    def test_non_owner_no_card_and_403_leaves_flag_unchanged(self, app: FastAPI) -> None:
        owner_email = "rbac-owner@example.com"
        member_email = "rbac-member@example.com"
        with app.state.session_factory() as session:
            owner = get_or_create_user(session, owner_email)
            ws = get_or_create_workspace(session, owner)
            member = get_or_create_user(session, member_email)
            session.add(WorkspaceMember(workspace_id=ws.id, user_id=member.id, role="member"))
            session.flush()
            set_active_workspace(session, member.id, ws.id)
            session.commit()
            ws_id = ws.id

        client = TestClient(app)
        member_hdr = {"X-User-Email": member_email}
        owner_hdr = {"X-User-Email": owner_email}

        owner_page = client.get("/settings", headers=owner_hdr)
        assert "Model improvement (cohort learning)" in owner_page.text

        member_page = client.get("/settings", headers=member_hdr)
        assert "Model improvement (cohort learning)" not in member_page.text

        resp = client.post(
            "/settings/cohort",
            headers=member_hdr,
            data={"cohort_opt_in": "1"},
            follow_redirects=False,
        )
        assert resp.status_code == 403

        with app.state.session_factory() as session:
            ws_after = session.get(Workspace, ws_id)
            assert ws_after is not None
            assert ws_after.cohort_opt_in is False


class TestAuditLogEntry:
    """T-COH-06: the flip is audit-logged like every data-use decision."""

    def test_opt_in_writes_auditlog_entry(self, app: FastAPI) -> None:
        email = "auditlog-owner@example.com"
        client = TestClient(app)
        hdr = {"X-User-Email": email}
        client.get("/settings", headers=hdr)  # creates the user (test_settings.py idiom)

        resp = client.post(
            "/settings/cohort", headers=hdr, data={"cohort_opt_in": "1"}, follow_redirects=False
        )
        assert resp.status_code == 303

        with app.state.session_factory() as session:
            entries = [
                e
                for e in session.execute(select(AuditLogEntry)).scalars()
                if e.action == "settings.cohort_opt_in"
            ]
        assert entries and entries[-1].subject == "opted in"


class TestAdminCohortExportRoute:
    """T-COH-07: GET /admin/cohort-export.json — token-gated, honest 404 below
    the floor, a real download when live."""

    def test_floor_gate_live_download_and_token_gate(
        self, app: FastAPI, settings: Settings
    ) -> None:
        app.state.settings.admin_token = "test-admin-token"
        client = TestClient(app)
        hdr = {"X-Admin-Token": "test-admin-token"}

        below = client.get(f"/admin/cohort-export.json?period={PERIOD}", headers=hdr)
        assert below.status_code == 404
        assert "10" in below.json()["detail"]

        _seed_baseline_cohort(app, n=10, when=PERIOD_DT, email_prefix="adminqual")

        live = client.get(f"/admin/cohort-export.json?period={PERIOD}", headers=hdr)
        assert live.status_code == 200
        body = live.json()
        assert body["schema_version"] == "1.0"
        assert body["period"] == PERIOD
        assert body["k"] == 10
        assert len(body["envelopes"]) == 10
        assert f"cohort-export-{PERIOD}.json" in live.headers["content-disposition"]

        assert client.get(f"/admin/cohort-export.json?period={PERIOD}").status_code == 404
        wrong = client.get(
            f"/admin/cohort-export.json?period={PERIOD}", headers={"X-Admin-Token": "wrong"}
        )
        assert wrong.status_code == 404


class TestDeterminism:
    """T-COH-08: a pure read over a total sort key — two builds of the same DB
    for the same period are byte-identical."""

    def test_two_builds_serialize_byte_identical(self, app: FastAPI, settings: Settings) -> None:
        _seed_baseline_cohort(app, n=10, when=PERIOD_DT, email_prefix="determinism")

        with app.state.session_factory() as session:
            exp1 = export.build(session, settings, settings.secret_key, PERIOD)
        with app.state.session_factory() as session:
            exp2 = export.build(session, settings, settings.secret_key, PERIOD)

        assert json.dumps(exp1.to_dict()) == json.dumps(exp2.to_dict())


class TestPseudonymSpaces:
    """T-COH-09: workspace_ref is a DISTINCT reference space from frame.py's
    user pseudonym, and raw workspace ids never ride along in the export."""

    def test_workspace_ref_differs_from_user_pseudonym_for_the_same_input(self) -> None:
        x = "some-shared-identifier"
        assert export.workspace_ref("test-secret", x) != frame.cohort_pseudonym("test-secret", x)

    def test_raw_workspace_ids_never_appear_in_the_serialized_export(
        self, app: FastAPI, settings: Settings
    ) -> None:
        rows = _seed_baseline_cohort(app, n=10, when=PERIOD_DT, email_prefix="pseudonym")

        with app.state.session_factory() as session:
            exp = export.build(session, settings, settings.secret_key, PERIOD)

        blob = json.dumps(exp.to_dict())
        for workspace_id, _audit_id in rows:
            assert workspace_id not in blob


class TestFr22MarkerAbsence:
    """T-COH-10: no seeded free text — workspace name, artifact route/tag,
    rationale copy — may survive into the serialized export; only counts and
    ratios under an opaque reference may leave."""

    def test_seeded_markers_absent_counts_present(self, app: FastAPI, settings: Settings) -> None:
        target_id = "ws" + "1" * 30
        marker_name = "SECRET-WS-NAME-MARKER"
        marker_route = "SECRET-ROUTE-MARKER"
        marker_rationale = "SECRET-RATIONALE-MARKER"

        with app.state.session_factory() as session:
            uid = new_id()
            session.add(User(id=uid, email="fr22-target@example.com"))
            session.add(Workspace(id=target_id, name=marker_name, cohort_opt_in=True))
            session.add(WorkspaceMember(workspace_id=target_id, user_id=uid, role="owner"))
            audit_id = _seed_done_audit(
                session, uid, target_id, when=PERIOD_DT, total_spend_usd=10.0
            )
            session.commit()

        _write_shapes_artifact(
            settings,
            audit_id,
            [{"route": marker_route, "shape": "STEADY", "rationale": marker_rationale}],
        )
        _seed_baseline_cohort(app, n=9, when=PERIOD_DT, email_prefix="fr22other")

        with app.state.session_factory() as session:
            exp = export.build(session, settings, settings.secret_key, PERIOD)
        assert exp.live

        blob = json.dumps(exp.to_dict())
        assert marker_name not in blob
        assert marker_route not in blob
        assert marker_rationale not in blob

        target_ref = export.workspace_ref(settings.secret_key, target_id)
        target_envelope = next(e for e in exp.envelopes if e.workspace_ref == target_ref)
        # the COUNT the marker route fed into still comes through, honestly
        assert target_envelope.features.shape_mix["STEADY"] == 1.0


class TestSchemaSelfAudit:
    """T-COH-11: the module's own schema self-audit reports clean."""

    def test_no_schema_violations(self) -> None:
        assert export.schema_violations() == []

    def test_off_pattern_detector_warns_never_silently_drops(
        self, app: FastAPI, settings: Settings, caplog
    ) -> None:
        """cold-review #97 f.1: a detector name outside the dN_* convention is
        excluded from fire rates WITH a warning naming it — never silently."""
        with app.state.session_factory() as session:
            uid, wsid = _seed_workspace(session, "offpattern@example.com", opt_in=True)
            audit_id = _seed_done_audit(session, uid, wsid, when=PERIOD_DT)
            session.add(
                FindingRow(
                    audit_id=audit_id,
                    finding_id="X-000",
                    detector="exotic_new_detector",
                    route=None,
                    severity="low",
                    monthly_impact_usd=1.0,
                    confidence="estimated",
                    fix_text="n/a",
                    evidence_sample=[],
                )
            )
            session.commit()
            audits = list(
                session.execute(select(Audit).where(Audit.workspace_id == wsid)).scalars()
            )
            with caplog.at_level("WARNING"):
                feats = export._features(session, settings, audits)
        assert "exotic_new_detector" in caplog.text
        assert all(rate == 0.0 for rate in feats.detector_fire_rates.values())

    def test_detector_keys_pin_the_registry(self) -> None:
        """export.py may not import the engine (T-FLY-07/R-F4), so its
        DETECTOR_KEYS is a literal — THIS test is where the literal meets
        the registry, so membership drift fails loudly, never silently."""
        from tokenops_cost_auditor.services.rules.registry import DETECTORS

        assert tuple(d.name.split("_", 1)[0] for d in DETECTORS) == export.DETECTOR_KEYS


class TestPeriodDiscipline:
    """T-COH-12: an opted-in workspace whose only done audit falls in a
    DIFFERENT period never enters this period's export."""

    def test_audit_in_other_period_not_counted(self, app: FastAPI, settings: Settings) -> None:
        _seed_baseline_cohort(app, n=10, when=PERIOD_DT, email_prefix="perioddisc")

        with app.state.session_factory() as session:
            uid, wsid = _seed_workspace(session, "other-period@example.com", opt_in=True)
            _seed_done_audit(session, uid, wsid, when=OTHER_PERIOD_DT)
            session.commit()
        target_ref = export.workspace_ref(settings.secret_key, wsid)

        with app.state.session_factory() as session:
            exp = export.build(session, settings, settings.secret_key, PERIOD)

        assert exp.k == 10
        assert all(e.workspace_ref != target_ref for e in exp.envelopes)
