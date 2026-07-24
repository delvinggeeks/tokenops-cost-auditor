"""Thin repositories + engine/session factory (docs/03-LLD.md §1)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, func, select
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


def get_or_create_workspace(session: Session, user: User) -> Workspace:
    """O-0 (R-ORG): the user's personal workspace (their owner membership),
    created on first need. In O-0 every user has exactly one. Idempotent and
    self-healing — the write-path calls it to resolve a resource's owner."""
    ws = session.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id, WorkspaceMember.role == "owner")
    )
    if ws is None:
        ws = Workspace(name=(f"{user.email}'s workspace")[:80], personal=True)
        session.add(ws)
        session.flush()
        session.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        session.flush()
    return ws


def workspace_id_for(session: Session, user_id: str) -> str | None:
    """The id of the user's owning workspace (O-0: their workspace-of-one).
    Used at resource-creation sites to stamp workspace_id. Returns None only if
    the user row is gone — callers leave workspace_id NULL, which the 1:1
    user_id scoping still handles correctly in O-0."""
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
