"""Append-only audit_log writer (FR-21; docs/02-HLD.md C6).

This module only ever INSERTs. No update/delete function exists here by design;
the DB role loses UPDATE/DELETE grants at deploy (docs/03-LLD.md §6).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import AuditLogEntry


def append(
    session: Session, actor: str, action: str, subject: str, detail: dict[str, object] | None = None
) -> None:
    session.add(AuditLogEntry(actor=actor, action=action, subject=subject, detail=detail or {}))
