"""Thin repositories + engine/session factory (docs/03-LLD.md §1)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from tokenops_cost_auditor.persistence.models import Audit, IdempotencyKey, User


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
    return user


def find_idempotent_audit(session: Session, user_id: str, key: str) -> Audit | None:
    """FR-26: an existing (user, key) pair returns the original audit."""
    row = session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )
    if row is None:
        return None
    return session.get(Audit, row.audit_id)


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
