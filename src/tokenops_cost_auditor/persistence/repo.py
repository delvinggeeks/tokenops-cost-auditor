"""Thin repositories + engine/session factory (docs/03-LLD.md §1)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tokenops_cost_auditor.persistence.models import (
    Audit,
    IdempotencyKey,
    User,
    Workspace,
    WorkspaceMember,
)


def make_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("postgresql"):
        # Bounded connect wait so /healthz degrades fast instead of hanging (NFR-05).
        connect_args["connect_timeout"] = 2
    if database_url.startswith("sqlite"):
        # allow session use from BackgroundTasks worker threads (tests/dev)
        connect_args["check_same_thread"] = False
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_or_create_user(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        user = User(email=email.lower())
        session.add(user)
        session.flush()
        # O-0 (R-ORG): every user is a workspace-of-one the moment they exist.
        get_or_create_workspace(session, user)
    return user


def _owner_workspace(session: Session, user_id: str) -> Workspace | None:
    return session.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.role == "owner")
    )


def get_or_create_workspace(session: Session, user: User) -> Workspace:
    """O-0 (R-ORG): the user's personal workspace (their owner membership),
    created on first need. Exactly one per user — the uq_owner_membership_per_user
    partial unique index makes that a DB fact, not an incidental one. Race-safe
    (cold-reviewer O-0 f.1): a concurrent caller that loses the insert has its
    orphan workspace rolled back by the savepoint and re-reads the winner's."""
    ws = _owner_workspace(session, user.id)
    if ws is not None:
        return ws
    try:
        with session.begin_nested():
            ws = Workspace(name=(f"{user.email}'s workspace")[:80], personal=True)
            session.add(ws)
            session.flush()
            session.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
            session.flush()
        return ws
    except IntegrityError:
        existing = _owner_workspace(session, user.id)
        if existing is None:  # pragma: no cover - the index guarantees a winner
            raise
        return existing


def workspace_id_for(session: Session, user_id: str) -> str | None:
    """The id of the user's owning workspace (O-0: their workspace-of-one). Used
    at resource-creation sites to stamp workspace_id. Returns None when the user
    has no owner membership yet (e.g. a User created out-of-band before
    get_or_create_workspace ran) — callers then leave workspace_id NULL, which
    the 1:1 user_id scoping still handles correctly in O-0. The
    uq_owner_membership_per_user index guarantees at most one owner row, so this
    scalar is unambiguous."""
    return session.scalar(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user_id, WorkspaceMember.role == "owner"
        )
    )


def find_idempotent_audit(session: Session, user_id: str, key: str) -> Audit | None:
    """FR-26: an existing (user, key) pair returns the original audit."""
    row = session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )
    if row is None:
        return None
    return session.get(Audit, row.audit_id)


def create_audit(session: Session, user_id: str) -> Audit:
    """Repo-pattern creation (G4 architect note): routes never touch ORM directly."""
    audit = Audit(
        user_id=user_id,
        status="queued",
        workspace_id=workspace_id_for(session, user_id),  # O-0: stamp the owner
    )
    session.add(audit)
    session.flush()
    return audit


def get_user_audit(session: Session, audit_id: str, email: str) -> Audit | None:
    """Audit visible only to its owner (404-equivalence for others)."""
    audit = session.get(Audit, audit_id)
    if audit is None:
        return None
    owner = session.get(User, audit.user_id)
    if owner is None or owner.email != email.lower():
        return None
    return audit


def processing_count(session: Session) -> int:
    return int(
        session.scalar(select(func.count()).select_from(Audit).where(Audit.status == "processing"))
        or 0
    )


def queue_position(session: Session, audit: Audit) -> int:
    """1-based position among queued audits ordered by creation time (NFR-13)."""
    ahead = session.scalar(
        select(func.count())
        .select_from(Audit)
        .where(Audit.status == "queued", Audit.created_at < audit.created_at)
    )
    return int(ahead or 0) + 1
