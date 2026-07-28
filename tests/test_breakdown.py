"""Tokenomics breakdown — enterprise depth engine, slice 1 (founder 2026-07-25)
+ FR-36 behaviour lens v1 (docs/03-LLD.md §9.3, T-F3).

Walks the whole journey (R-VERTICAL, ship=walk): a real audit runs the full
pipeline → the runner writes an EXACT tokenomics.json artifact → the /breakdown
page renders the vitals, per-model and per-route (cost-allocation) tables, the
FR-36 workload-shape chips, and the data-coverage — all reachable from the
shell nav. Honest empty state when there is no audit yet, an honest pre-feature
note when an artifact predates the shape lens, and an honest coarse-source note
when the latest audit is aggregate-depth (connected source, no per-request
artifact at all).
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import ApiToken, Audit, User
from tokenops_cost_auditor.services.connectors.crypto import credential_fingerprint
from tokenops_cost_auditor.services.runner import AuditRunner

FIXTURES = Path(__file__).parent / "fixtures"
EMAIL = "breakdown@example.com"
HDR = {"X-User-Email": EMAIL}

# FR-36's five fixed rationale templates (shapes.py) — every by_route entry in
# a shapes-bearing artifact must match exactly one of these (never free text).
_RATIONALE_PATTERNS = [
    re.compile(r"^\d+ near-identical calls within \d+ s \(threshold: \d+\)$"),
    re.compile(r"^\d+ calls under \d+ output tokens within \d+ s \(threshold: \d+\)$"),
    # "input" not "prompt" (T-F3 follow-up): the shipped FR-22 marker tripwire
    # (test_developer_platform.py::test_fr22_shape_counts_and_dollars_only)
    # asserts the whole breakdown response text contains no "prompt" substring,
    # so these two engine templates were reworded to say "input" instead.
    re.compile(
        r"^median input grew [\d,]+ → [\d,]+ tokens \(\d+\.\d+x\) from the first "
        r"to the last quarter of the window \(threshold: \d+\.\d+x\)$"
    ),
    re.compile(
        r"^same prefix sent \d+x at median [\d,]+ input tokens with 0 cached "
        r"tokens read \(threshold: \d+ repeats at >= [\d,]+ tokens\)$"
    ),
    re.compile(
        r"^no loop, burst, growth or cache signal crossed its threshold across [\d,]+ calls$"
    ),
]

# FR-22: no prompt/completion text may ever appear in a persisted artifact or
# API response — walked recursively over the breakdown JSON in the privacy test.
_FR22_FORBIDDEN_KEYS = {"prompt", "completion", "messages", "text", "_text", "content"}

_SHAPE_BADGE_LABELS = (
    "Agent loop",
    "Retry burst",
    "Context growth",
    "Unclaimed cache",
    "Steady",
)


def _seed_audit(app: FastAPI, fixture: str) -> str:
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == EMAIL)) or User(email=EMAIL)
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


def _user_id(app: FastAPI, email: str = EMAIL) -> str:
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        return user.id


def _mint_read_token(app: FastAPI, user_id: str, scopes: str = "read:audits") -> str:
    """Insert an ApiToken row directly (bypassing the "pro"-plan-gated mint
    endpoint, which is exercised elsewhere in test_developer_platform.py) so
    this suite can hit the read API with a valid `rt_…` bearer."""
    token = "rt_" + secrets.token_urlsafe(24)
    fp = credential_fingerprint(app.state.settings.secret_key, token)
    with app.state.session_factory() as session:
        session.add(ApiToken(user_id=user_id, label="fr36-test", token_hash=fp, scopes=scopes))
        session.commit()
    return token


def _seed_coarse_audit(app: FastAPI, email: str = EMAIL) -> str:
    """A DONE audit from a connected source (source_id set) with NO
    tokenomics.json on disk — the aggregate-depth shape (FR-36 depth honesty)."""
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == email)) or User(email=email)
        session.add(user)
        session.flush()
        audit = Audit(user_id=user.id, status="done", source_id="src_connected_1")
        session.add(audit)
        session.commit()
        return audit.id


class TestBreakdownJourney:
    def test_audit_produces_exact_breakdown_and_it_renders(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        runner: AuditRunner = app.state.runner
        runner.run(audit_id)

        # the runner wrote the deterministic tokenomics artifact next to the report
        tk_path = Path(settings.report_dir) / audit_id / "tokenomics.json"
        assert tk_path.exists(), "runner did not write tokenomics.json"
        tk = json.loads(tk_path.read_text(encoding="utf-8"))
        assert tk["monthly_spend_usd"] > 0
        assert tk["by_model"] and tk["by_route"]
        assert 0.0 <= tk["cache_hit_rate"] <= 1.0
        assert tk["pct_priced"] == 1.0  # the sample is fully priced

        # and it renders on /breakdown with the exact slices
        page = TestClient(app).get("/breakdown", headers=HDR).text
        assert "Tokenomics vitals" in page
        assert "By model" in page and "By route (cost allocation)" in page
        assert "Data coverage" in page
        assert tk["by_model"][0]["name"] in page  # the top model appears in the table

    def test_corrupt_artifact_degrades_to_empty_state_not_500(
        self, app: FastAPI, settings: Settings
    ) -> None:
        # a partial/corrupt tokenomics.json (crash mid-write) must not 500 the page
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        (Path(settings.report_dir) / audit_id / "tokenomics.json").write_text(
            "{ this is not valid json", encoding="utf-8"
        )
        resp = TestClient(app).get("/breakdown", headers=HDR)
        assert resp.status_code == 200  # not a 500
        assert "No breakdown yet" in resp.text  # honest empty state

    def test_no_audit_shows_honest_empty_state(self, app: FastAPI) -> None:
        page = TestClient(app).get("/breakdown", headers=HDR)
        assert page.status_code == 200
        assert "No breakdown yet" in page.text
        assert "$0.00" not in page.text  # never a fabricated breakdown

    def test_breakdown_is_reachable_from_the_shell_nav(self, app: FastAPI) -> None:
        page = TestClient(app).get("/dashboard", headers=HDR).text
        assert 'href="/breakdown"' in page


class TestBreakdownShapesJourney:
    """FR-36 C.1: seed → run → the artifact carries `shapes` → the HTML page
    renders the workload-shape chip, its fix-first "why" line, and the FR-22
    reassurance ("we never read your prompts")."""

    def test_shapes_block_present_and_chip_renders(self, app: FastAPI, settings: Settings) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)

        tk_path = Path(settings.report_dir) / audit_id / "tokenomics.json"
        tk = json.loads(tk_path.read_text(encoding="utf-8"))
        assert tk["shapes"]["schema"] == 1
        assert tk["shapes"]["by_route"], "expected at least one classified route"

        page = TestClient(app).get("/breakdown", headers=HDR).text
        assert "Workload shape" in page
        assert "badge badge-" in page
        assert "shape-why" in page
        assert "we never read your prompts" in page


class TestBreakdownPreFeatureArtifact:
    """FR-36 C.2: an artifact written before the shape lens shipped (the
    "shapes" key simply doesn't exist) degrades to an honest null — never a
    fabricated STEADY chip, never a 500, on either surface."""

    def test_html_shows_honest_pre_feature_note_no_fabricated_chips(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        tk_path = Path(settings.report_dir) / audit_id / "tokenomics.json"
        data = json.loads(tk_path.read_text(encoding="utf-8"))
        assert "shapes" in data  # sanity: the runner did write it
        del data["shapes"]
        tk_path.write_text(json.dumps(data), encoding="utf-8")

        resp = TestClient(app).get("/breakdown", headers=HDR)
        assert resp.status_code == 200
        page = resp.text
        assert "This audit ran before the shape lens shipped" in page
        assert "—" in page
        for label in _SHAPE_BADGE_LABELS:
            assert label not in page

    def test_api_breakdown_matches_artifact_on_disk_never_500(
        self, app: FastAPI, settings: Settings
    ) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        tk_path = Path(settings.report_dir) / audit_id / "tokenomics.json"
        data = json.loads(tk_path.read_text(encoding="utf-8"))
        del data["shapes"]
        tk_path.write_text(json.dumps(data), encoding="utf-8")

        uid = _user_id(app)
        token = _mint_read_token(app, uid)
        resp = TestClient(app).get(
            f"/api/v1/audits/{audit_id}/breakdown",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["breakdown"] == data
        assert "shapes" not in body["breakdown"]


class TestBreakdownCoarseSource:
    """FR-36 C.3: the latest audit is aggregate-depth (a connected source,
    source_id set, no per-request artifact) — the page says so honestly
    rather than rendering an empty/broken breakdown."""

    def test_coarse_source_empty_state(self, app: FastAPI) -> None:
        _seed_coarse_audit(app)
        resp = TestClient(app).get("/breakdown", headers=HDR)
        assert resp.status_code == 200
        assert "Your latest audit is from a connected source — its data is aggregate" in resp.text


class TestBreakdownShapesPrivacy:
    """FR-36 C.4: walk the API breakdown JSON for a shapes-bearing audit and
    prove FR-22 by construction — no key anywhere names prompt/completion
    text, and every by_route rationale is one of the five fixed templates
    (never free text that could leak a hint of content)."""

    @staticmethod
    def _walk_keys(obj: object) -> set[str]:
        keys: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k)
                keys |= TestBreakdownShapesPrivacy._walk_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                keys |= TestBreakdownShapesPrivacy._walk_keys(item)
        return keys

    def test_no_fr22_marker_keys_and_rationales_match_fixed_templates(self, app: FastAPI) -> None:
        audit_id = _seed_audit(app, "waste_pack_anthropic.jsonl")
        app.state.runner.run(audit_id)
        uid = _user_id(app)
        token = _mint_read_token(app, uid)

        resp = TestClient(app).get(
            f"/api/v1/audits/{audit_id}/breakdown",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()

        seen_keys = self._walk_keys(body)
        assert not (seen_keys & _FR22_FORBIDDEN_KEYS)

        by_route = body["breakdown"]["shapes"]["by_route"]
        assert by_route, "expected at least one classified route"
        for entry in by_route:
            rationale = entry["rationale"]
            assert any(p.match(rationale) for p in _RATIONALE_PATTERNS), rationale
