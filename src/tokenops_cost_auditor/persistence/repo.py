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


def _is_member(session: Session, user_id: str, workspace_id: str) -> bool:
    """True if the user currently holds ANY membership in the workspace (O-1b).
    The LIVE check that keeps active_workspace_id leak-safe: a revoked member, or
    a pointer to a workspace the user never joined, is not a member — so the
    resolver falls back to personal rather than scope a read to foreign data."""
    return (
        session.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        is not None
    )


def active_workspace_id(session: Session, user_id: str) -> str | None:
    """O-1: the workspace the user is currently acting in — the READ scope for
    every owned resource. O-1b: their `User.active_workspace_id` IF they still
    hold a membership in it, otherwise their personal workspace. EVERY read of an
    owned resource scopes to THIS, never to user_id — that is what makes a
    workspace's members see the same data.

    LEAK-SAFETY (load-bearing, two guarantees):
    1. The returned workspace is ALWAYS one the caller is a member of — a
       switched pointer is validated against live membership (`_is_member`), so a
       revoked member or a stale/foreign `active_workspace_id` silently falls
       back to personal and never scopes a read to another tenant's data.
    2. It is NEVER None for a real user — a read scoped `Model.workspace_id ==
       active_workspace_id(...)` must not become `IS NULL` (which would match
       every tenant's un-stamped rows). The personal workspace is ensure-created
       if missing. None is returned ONLY when user_id names no user at all — an
       impossible input on an authenticated read path; T-ORG tests pin both."""
    user = session.get(User, user_id)
    if user is None:  # pragma: no cover - unreachable on an authenticated path
        return None
    personal = workspace_id_for(session, user_id)
    if personal is None:
        personal = get_or_create_workspace(session, user).id
    active = user.active_workspace_id
    if active and active != personal and _is_member(session, user_id, active):
        return active
    return personal


def set_active_workspace(session: Session, user_id: str, workspace_id: str) -> bool:
    """O-1b: switch the user's active workspace. Returns False and changes
    nothing unless the user is a member of the target — a user can only ever act
    in a workspace they belong to (the switch cannot become a privilege grant)."""
    user = session.get(User, user_id)
    if user is None or not _is_member(session, user_id, workspace_id):
        return False
    user.active_workspace_id = workspace_id
    return True


def list_memberships(session: Session, user_id: str) -> list[tuple[Workspace, str]]:
    """Every workspace the user belongs to, with their role — for the workspace
    switcher and the Members surface. Their personal workspace is included."""
    rows = session.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.created_at)
    ).all()
    return [(ws, role) for ws, role in rows]


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
    """Audit visible to any member of its workspace (404-equivalence for others).

    O-1 (R-ORG): scoped to the caller's ACTIVE WORKSPACE, not just the owner's
    email — a workspace member can view the workspace's audits/reports/findings.
    Behavior-preserving while 1 user = 1 workspace (the caller's active
    workspace == their personal workspace == their own audits' workspace_id).
    This is an EMAIL-based ownership check the `.user_id ==` sweep grep did not
    surface; it is a genuine tenant-scoping read and re-scopes here."""
    audit = session.get(Audit, audit_id)
    if audit is None:
        return None
    caller = session.scalar(select(User).where(User.email == email.lower()))
    if caller is None:
        return None
    # active_workspace_id never returns None for a real user (leak-safety note
    # there); a NULL-workspace audit therefore never matches and stays hidden.
    return audit if audit.workspace_id == active_workspace_id(session, caller.id) else None


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
