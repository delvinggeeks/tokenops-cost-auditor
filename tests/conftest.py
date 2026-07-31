import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session as _SASession

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.main import create_app
from tokenops_cost_auditor.persistence.models import (
    AlertCheck,
    AlertEvent,
    AlertRule,
    ApiToken,
    Audit,
    Base,
    Device,
    IngestKey,
    OAuthApp,
    SavedView,
    Source,
    Statement,
    Subscription,
    User,
    Workspace,
    WorkspaceMember,
    new_id,
)

# LE-7 (docs/09-SDLC.md §6, ADR-8) needs the pytester fixture for its own
# guard/probe tests of the verifies_requirement marker.
pytest_plugins = ["pytester"]

# --- LE-7 requirement-id guard (docs/09-SDLC.md §6) --------------------------
# @pytest.mark.verifies_requirement(<id>) is the single source of the
# requirement<->test edge (docs/04 becomes DERIVED, not authored). A marker
# naming an id absent from docs/01-REQUIREMENTS.md fails collection so a typo
# or a stale id can never silently masquerade as traceability.
_REQUIREMENT_ID_RE = re.compile(r"^(FR|NFR)-\d+")


def _known_requirement_ids() -> frozenset[str]:
    doc = Path(__file__).resolve().parent.parent / "docs" / "01-REQUIREMENTS.md"
    return frozenset(
        m.group(0) for line in doc.read_text().splitlines() if (m := _REQUIREMENT_ID_RE.match(line))
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    known = _known_requirement_ids()
    unknown = [
        f"{item.nodeid}: verifies_requirement({marker.args[0]!r}) is not a "
        f"requirement id in docs/01-REQUIREMENTS.md"
        for item in items
        for marker in item.iter_markers(name="verifies_requirement")
        if marker.args[0] not in known
    ]
    if unknown:
        raise pytest.UsageError("\n".join(unknown))


# --- O-1 test-fixture parity (R-ORG) -----------------------------------------
# Production stamps workspace_id at every create site (O-0) and mints each user
# a workspace-of-one at first login (repo.get_or_create_user). Test fixtures,
# by contrast, build rows RAW — `User(email=...)`, `Audit(user_id=...)` — which
# O-0 tolerated (reads were user_id-scoped) but O-1 does not (reads scope to
# workspace_id via repo.active_workspace_id). This before_flush hook makes raw
# fixtures obey the same write contract as production, and ONLY for gaps:
#   * a new User lacking an owner membership gets its workspace-of-one, and
#   * an owned row with workspace_id IS NULL inherits its owner's workspace.
# It NEVER overrides a workspace_id that is already set, so the production
# create-site stamping (create_audit et al., which set a real value) is still
# exercised unchanged by test_workspace_spine.TestWritePathStamps — this hook
# cannot mask a missing-stamp production bug, because those paths set non-None.
# Bonus: giving raw users a real workspace keeps active_workspace_id on its fast
# path (no repeated ensure-create) instead of thrashing on every read.
_OWNED_BY: list[tuple[type, str]] = [
    (Audit, "user_id"),
    (Source, "user_id"),
    (IngestKey, "user_id"),
    (ApiToken, "user_id"),
    (Device, "user_id"),
    (AlertRule, "user_id"),
    (Subscription, "user_id"),
    (Statement, "user_id"),
    (SavedView, "user_id"),
    (OAuthApp, "owner_user_id"),
    # O-1b: operational logs gained workspace_id (member visibility). Payment
    # is intentionally absent — it has no workspace_id (billing is O-2).
    (AlertEvent, "user_id"),
    (AlertCheck, "user_id"),
]


@event.listens_for(_SASession, "before_flush")
def _stamp_workspace_on_fixtures(
    session: _SASession, flush_context: object, instances: object
) -> None:
    ws_of: dict[str, str] = {
        o.user_id: o.workspace_id
        for o in session.new
        if isinstance(o, WorkspaceMember) and o.role == "owner"
    }
    for u in [o for o in session.new if isinstance(o, User)]:
        if u.id is None:
            u.id = new_id()
        if u.id in ws_of:
            continue
        ws = Workspace(id=new_id(), name=(f"{u.email}'s workspace")[:80], personal=True)
        session.add(ws)
        session.add(WorkspaceMember(id=new_id(), workspace_id=ws.id, user_id=u.id, role="owner"))
        ws_of[u.id] = ws.id

    def _resolve(uid: str) -> str | None:
        if uid not in ws_of:
            with session.no_autoflush:
                ws_of[uid] = session.scalar(
                    select(WorkspaceMember.workspace_id).where(
                        WorkspaceMember.user_id == uid, WorkspaceMember.role == "owner"
                    )
                )
        return ws_of[uid]

    for obj in session.new:
        for model, attr in _OWNED_BY:
            if isinstance(obj, model) and getattr(obj, "workspace_id", None) is None:
                uid = getattr(obj, attr, None)
                if uid:
                    obj.workspace_id = _resolve(uid)
                break


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Unit-test settings: sqlite keeps L1 tests DB-independent; L2 integration
    tests (D6+) use DATABASE_URL from the environment (real postgres in CI)."""
    return Settings(
        app_env="test",
        secret_key="test-secret",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        backup_dir=tmp_path / "backups",
        _env_file=None,
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """The slowapi limiter is a module-level global whose per-key counters
    persist ACROSS tests (readiness audit 2026-07-22 — a flaky suite). One
    test spending the 5/min /auth/signin-link budget made a LATER test's
    sign-in helper 429 and IndexError. Clear the limiter's storage before
    every test so rate-limit state can't leak between them."""
    from tokenops_cost_auditor.obs.ratelimit import limiter

    try:
        limiter.reset()
    except Exception:
        storage = getattr(limiter, "_storage", None)
        if storage is not None and hasattr(storage, "reset"):
            storage.reset()
    yield


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def ci_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("postgres DATABASE_URL not configured")
    return url
