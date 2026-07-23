"""M-FLY-0 A1 — the training-frame contract (docs/12 Stage 3, Track A).

The ONE shape every learning rung (L1 benchmarks, L2 calibration, learned
L3) consumes. Laws enforced AT THIS DOOR, not downstream:

- FR-22: counts, enums and opaque ids only. FRAME_COLUMNS is the schema and
  ENUM_OR_ID_FIELDS names every string column that may exist; the test
  suite fails any field outside them, so a free-text column cannot ship.
- R-F1-SIGNOFF: accounts with benchmark_sharing=False NEVER enter the
  frame — excluded means excluded from the first byte.
- R-Q9: savings_realized_usd is customer-reported passthrough, carried for
  label quality only; it never merges into any verified figure.
- Determinism: extraction is a pure function of DB state; rows sort on a
  total key so two extracts are byte-identical.
- Pseudonymity: customer identity is a keyed one-way HMAC under an HKDF
  context distinct from credential encryption; unrecoverable without
  SECRET_KEY, stable per customer so longitudinal learning works.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, fields
from hashlib import sha256

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.persistence.models import (
    Audit,
    FindingFeedback,
    FindingRow,
    User,
)

_HKDF_INFO = b"tokenops-flywheel-cohort"

# The schema of record. A field added to TrainingRow without a matching
# entry here fails T-FLY-02 — additions are deliberate, never drive-by.
FRAME_COLUMNS = (
    "customer",
    "audit_id",
    "tier",
    "detector",
    "route",
    "severity",
    "confidence",
    "baseline_monthly_usd",
    "verdict",
    "savings_realized_usd",
    "audit_row_count",
    "audit_observed_days",
    "audit_when",
)

# Every string-typed column, each id- or enum-shaped by construction.
# A new str field NOT named here fails the schema test — that is the
# "no free-text column can ship" law in executable form.
ENUM_OR_ID_FIELDS = frozenset(
    {
        "customer",  # HMAC pseudonym
        "audit_id",  # random hex
        "tier",  # upload | connected
        "detector",  # d1..d6 registry ids
        "route",  # model id, when the detector names one
        "severity",  # high | med | low
        "confidence",  # estimated | conservative
        "verdict",  # applied | dismissed | not_relevant | None
        "audit_when",  # ISO date
    }
)


def cohort_pseudonym(secret_key: str, user_id: str) -> str:
    """Stable, keyed, one-way customer identity for cross-customer learning."""
    material = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        secret_key.encode()
    )
    return hmac.new(material, user_id.encode(), sha256).hexdigest()


@dataclass(frozen=True)
class TrainingRow:
    customer: str
    audit_id: str
    tier: str
    detector: str
    route: str | None
    severity: str
    confidence: str
    baseline_monthly_usd: float
    verdict: str | None
    savings_realized_usd: float | None
    audit_row_count: int
    audit_observed_days: int
    audit_when: str


def extract(session: Session, secret_key: str) -> list[TrainingRow]:
    """Deterministic counts-only extract of every finding the cohort may
    learn from. Zero network, zero inference — a pure read."""
    included_users = {
        u.id: u
        for u in session.execute(select(User)).scalars()
        if u.benchmark_sharing is not False  # R-F1: excluded means excluded
    }
    audits = {
        a.id: a
        for a in session.execute(select(Audit).where(Audit.status == "done")).scalars()
        if a.user_id in included_users
    }
    if not audits:
        return []
    verdicts: dict[tuple[str, str], FindingFeedback] = {
        (fb.audit_id, fb.finding_id): fb
        for fb in session.execute(
            select(FindingFeedback).where(FindingFeedback.audit_id.in_(audits))
        ).scalars()
    }
    rows: list[TrainingRow] = []
    for fr in (
        session.execute(select(FindingRow).where(FindingRow.audit_id.in_(audits))).scalars().all()
    ):
        audit = audits[fr.audit_id]
        fb = verdicts.get((fr.audit_id, fr.finding_id))
        when = audit.report_ready_at or audit.created_at
        rows.append(
            TrainingRow(
                customer=cohort_pseudonym(secret_key, audit.user_id),
                audit_id=audit.id,
                tier="connected" if audit.paid_via == "subscription" else "upload",
                detector=fr.detector,
                route=fr.route,
                severity=fr.severity,
                confidence=fr.confidence,
                baseline_monthly_usd=round(float(fr.monthly_impact_usd), 2),
                verdict=fb.verdict if fb is not None else None,
                savings_realized_usd=(
                    round(float(fb.savings_realized_usd), 2)
                    if fb is not None and fb.savings_realized_usd is not None
                    else None
                ),
                audit_row_count=int(audit.row_count or 0),
                audit_observed_days=int(audit.observed_days or 0),
                audit_when=f"{when:%Y-%m-%d}",
            )
        )
    rows.sort(key=lambda r: (r.audit_when, r.audit_id, r.detector, r.route or "", r.severity))
    return rows


def schema_violations() -> list[str]:
    """Self-audit used by T-FLY-02: every field in FRAME_COLUMNS, every str
    field enum/id-shaped. Returns problems instead of asserting so the test
    output names the offending field."""
    problems: list[str] = []
    declared = [f.name for f in fields(TrainingRow)]
    if tuple(declared) != FRAME_COLUMNS:
        problems.append(f"fields {declared} != FRAME_COLUMNS {list(FRAME_COLUMNS)}")
    for f in fields(TrainingRow):
        if "str" in str(f.type) and f.name not in ENUM_OR_ID_FIELDS:
            problems.append(f"str-typed field {f.name!r} not in ENUM_OR_ID_FIELDS")
    return problems
