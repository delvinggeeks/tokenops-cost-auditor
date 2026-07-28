"""T-F2 · FR-35 — CohortExportEnvelope v1 (LLD §9.1): the factory's ONLY inlet.

Aggregate features ONLY — counts and ratios under an opaque workspace
reference. Consent is `workspaces.cohort_opt_in`: EXPLICIT opt-in, default
false — the opposite direction from `User.benchmark_sharing` (R-F1 opt-out),
because this is the one path any data takes OUT of the product. k-anonymity
floor: envelopes exist only when the opted-in cohort with audited usage in
the period reaches `flywheel_l1_min_customers` (the L1 threshold); below it
the export is an honest refusal that names n and the floor, never a file.

Tenancy is stripped HERE, at the persistence boundary (HLD §8.2):
`workspace_ref` is a keyed one-way pseudonym under an HKDF info context
DISTINCT from frame.py's user pseudonym, so the two reference spaces can
never collide or be joined. `services/rules` and `services/pricing` never
learn the word "cohort" (tenant-blind law, R-ORG).

Feature keys are LLD §9.1 verbatim. `detector_fire_rates` keys are the short
"dN" ids derived from the shipped registry — NINE detectors; d7 never
shipped, and the registry is authoritative over the LLD's "d1..d10" span
notation. A fire rate is the share of the workspace's period audits in which
that detector raised at least one finding. `shape_mix` keys are the five
ShapeClass values (FR-36), aggregated from each audit's persisted
tokenomics.json shapes block — passthrough, no reclassification (HLD §8.3).

No new money math: `monthly_spend_usd` sums audited `total_spend_usd`
figures (passthrough arithmetic) — no pricing golden impact. Deterministic:
a pure read over a total sort key; two exports of the same DB for the same
period are byte-identical.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from hashlib import sha256

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import (
    Audit,
    CallAggregate,
    FindingRow,
    Workspace,
)
from tokenops_cost_auditor.services.dashboard.shapes import ShapeClass
from tokenops_cost_auditor.services.dashboard.tokenomics import load_artifact

SCHEMA_VERSION = "1.0"

# DISTINCT info context from frame.py's user pseudonym (same SECRET_KEY,
# different derivation) — the workspace and user reference spaces must never
# collide or join.
_HKDF_INFO = b"tokenops-cohort-export-workspace"

# Short "dN" envelope keys (LLD §9.1): the nine shipped detector ids in
# registry order, as a LITERAL — the flywheel package never imports the
# engine (T-FLY-07/R-F4), so the registry cannot be read from here.
# tests/test_cohort_export.py pins this tuple against rules/registry
# DETECTORS; drift fails the suite, never silently.
DETECTOR_KEYS: tuple[str, ...] = ("d1", "d2", "d3", "d4", "d5", "d6", "d8", "d9", "d10")
SHAPE_KEYS: tuple[str, ...] = tuple(c.value for c in ShapeClass)

# The schema of record (frame.py pattern): a field added to Features without
# a matching entry here fails the schema self-audit — additions are
# deliberate, never drive-by.
FEATURE_KEYS = (
    "monthly_spend_usd",
    "tokens_in",
    "tokens_out",
    "tokens_cached",
    "cache_hit_rate",
    "out_in_ratio",
    "detector_fire_rates",
    "shape_mix",
)


def workspace_ref(secret_key: str, workspace_id: str) -> str:
    """Stable, keyed, one-way workspace identity — never the id (LLD §9.1)."""
    material = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        secret_key.encode()
    )
    return hmac.new(material, workspace_id.encode(), sha256).hexdigest()


def current_period() -> str:
    """The export period for 'now' — callers may pass any explicit period."""
    return f"{datetime.now(UTC):%Y-%m}"


@dataclass(frozen=True)
class Features:
    monthly_spend_usd: float
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    cache_hit_rate: float
    out_in_ratio: float
    detector_fire_rates: dict[str, float]  # keys = DETECTOR_KEYS, always all nine
    shape_mix: dict[str, float]  # keys = SHAPE_KEYS, always all five

    def to_dict(self) -> dict[str, object]:
        return {
            "monthly_spend_usd": self.monthly_spend_usd,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_cached": self.tokens_cached,
            "cache_hit_rate": self.cache_hit_rate,
            "out_in_ratio": self.out_in_ratio,
            "detector_fire_rates": dict(self.detector_fire_rates),
            "shape_mix": dict(self.shape_mix),
        }


@dataclass(frozen=True)
class Envelope:
    schema_version: str
    period: str
    workspace_ref: str
    k: int
    features: Features

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "period": self.period,
            "workspace_ref": self.workspace_ref,
            "k": self.k,
            "features": self.features.to_dict(),
        }


@dataclass(frozen=True)
class CohortExport:
    period: str
    k: int  # opted-in workspaces with audited usage in the period
    floor: int  # the k-anonymity threshold that gated this export
    reason: str  # "" when live; the honest why-not otherwise (FR-35 "says why")
    envelopes: tuple[Envelope, ...]

    @property
    def live(self) -> bool:
        return not self.reason

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "period": self.period,
            "k": self.k,
            "envelopes": [e.to_dict() for e in self.envelopes],
        }


def _period_of(audit: Audit) -> str:
    when = audit.report_ready_at or audit.created_at
    return f"{when:%Y-%m}"


def _round4(value: float) -> float:
    return round(value, 4)


def _features(session: Session, settings: Settings, audits: list[Audit]) -> Features:
    audit_ids = sorted(a.id for a in audits)
    aggs = (
        session.execute(select(CallAggregate).where(CallAggregate.audit_id.in_(audit_ids)))
        .scalars()
        .all()
    )
    tokens_in = sum(int(r.prompt_tokens) for r in aggs)
    tokens_out = sum(int(r.completion_tokens) for r in aggs)
    tokens_cached = sum(int(r.cached_tokens) for r in aggs)

    fired: dict[str, set[str]] = {key: set() for key in DETECTOR_KEYS}
    for fr in (
        session.execute(select(FindingRow).where(FindingRow.audit_id.in_(audit_ids)))
        .scalars()
        .all()
    ):
        key = fr.detector.split("_", 1)[0]
        if key in fired:
            fired[key].add(fr.audit_id)
    n_audits = len(audit_ids)

    # shape_mix: passthrough of each audit's persisted shapes block. An audit
    # without the block (pre-feature / coarse source / purged artifact)
    # contributes nothing — absence stays absence, never a fabricated STEADY.
    shape_counts = dict.fromkeys(SHAPE_KEYS, 0)
    total_routes = 0
    for audit_id in audit_ids:
        artifact = load_artifact(settings.report_dir, audit_id) or {}
        block = artifact.get("shapes")
        rows = block.get("by_route", []) if isinstance(block, dict) else []
        for row in rows:
            shape = str(row.get("shape", "")) if isinstance(row, dict) else ""
            if shape in shape_counts:
                shape_counts[shape] += 1
                total_routes += 1

    return Features(
        monthly_spend_usd=round(
            sum(float(a.total_spend_usd) for a in audits if a.total_spend_usd is not None), 2
        ),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_cached=tokens_cached,
        cache_hit_rate=_round4(tokens_cached / tokens_in) if tokens_in else 0.0,
        out_in_ratio=_round4(tokens_out / tokens_in) if tokens_in else 0.0,
        detector_fire_rates={
            key: _round4(len(fired[key]) / n_audits) if n_audits else 0.0 for key in DETECTOR_KEYS
        },
        shape_mix={
            key: _round4(shape_counts[key] / total_routes) if total_routes else 0.0
            for key in SHAPE_KEYS
        },
    )


def build(session: Session, settings: Settings, secret_key: str, period: str) -> CohortExport:
    """The export, or the honest refusal — never an empty-but-valid file.

    Cohort membership = cohort_opt_in AND at least one done audit whose
    completion falls in `period`. k counts member workspaces; below
    `flywheel_l1_min_customers` NO envelope exists (LLD §9.1: "envelope
    EXISTS only when k>=10") and `reason` says why (FR-35 accept clause).
    """
    floor = settings.flywheel_l1_min_customers
    opted = {
        w.id
        for w in session.execute(select(Workspace)).scalars()
        if w.cohort_opt_in  # explicit opt-in only — None/False both stay out
    }
    audits_by_workspace: dict[str, list[Audit]] = {}
    if opted:
        for audit in session.execute(select(Audit).where(Audit.status == "done")).scalars():
            if audit.workspace_id in opted and _period_of(audit) == period:
                audits_by_workspace.setdefault(audit.workspace_id, []).append(audit)
    k = len(audits_by_workspace)
    if k < floor:
        return CohortExport(
            period=period,
            k=k,
            floor=floor,
            reason=(
                f"below the k-anonymity floor: {k} opted-in workspace(s) with audited "
                f"usage in {period}, {floor} required — nothing is exported"
            ),
            envelopes=(),
        )
    envelopes = sorted(
        (
            Envelope(
                schema_version=SCHEMA_VERSION,
                period=period,
                workspace_ref=workspace_ref(secret_key, workspace_id),
                k=k,
                features=_features(session, settings, audits),
            )
            for workspace_id, audits in audits_by_workspace.items()
        ),
        key=lambda e: e.workspace_ref,
    )
    return CohortExport(period=period, k=k, floor=floor, reason="", envelopes=tuple(envelopes))


def schema_violations() -> list[str]:
    """Self-audit (frame.py pattern, T-FLY-02 style): every feature declared
    in FEATURE_KEYS, NO str-typed feature (free text structurally cannot
    ship), dict keys pinned to the registry/enum tuples. Returns problems
    instead of asserting so test output names the offending field."""
    problems: list[str] = []
    declared = tuple(f.name for f in fields(Features))
    if declared != FEATURE_KEYS:
        problems.append(f"fields {list(declared)} != FEATURE_KEYS {list(FEATURE_KEYS)}")
    for f in fields(Features):
        if "str" in str(f.type) and "dict" not in str(f.type):
            problems.append(f"str-typed feature {f.name!r} — free text cannot ship")
    if len(DETECTOR_KEYS) != 9 or "d7" in DETECTOR_KEYS:
        problems.append(f"detector keys {list(DETECTOR_KEYS)} != the nine shipped ids (no d7)")
    if len(SHAPE_KEYS) != 5:
        problems.append(f"shape keys {list(SHAPE_KEYS)} != the five ShapeClass values")
    return problems
