"""M-FLY-2 — the cohort export envelope (FR-35; docs/01 §H; docs/03-LLD.md §9.1;
docs/02-HLD.md §8.2). The factory's ONLY inlet.

Laws enforced AT THIS DOOR:

- Consent: `Workspace.cohort_opt_in` (NOT NULL, default False) — explicit
  opt-in, checked at export time. Distinct flag from `User.benchmark_sharing`
  (R-F1, in-product benchmarks); this one governs data LEAVING to the factory.
- k-anonymity floor: `settings.flywheel_l1_min_customers` (the L1 threshold,
  reused rather than a second config knob). Fewer opted-in workspaces with a
  completed audit in the period than the floor -> ZERO envelopes, an honest
  reason naming n and the floor (FR-35 accept clause) — never a partial or
  fabricated export.
- Tenancy stripped HERE: `workspace_ref` is an opaque keyed HMAC, never the
  id, under an HKDF context DISTINCT from frame.py's user-pseudonym context
  so the two pseudonym spaces can never collide even under the same secret.
- Aggregate-only: every feature is a count, ratio or rate keyed by a fixed,
  enum/id-shaped vocabulary (`FEATURE_KEYS`, `DETECTOR_IDS`, `SHAPE_KEYS`) —
  no names, routes, tags or text (R-ZTA/FR-22). `envelope_violations` is the
  executable schema self-audit: a free-text field cannot ship undetected.
- No new money math: `monthly_spend_usd`/token vitals are a PASSTHROUGH of
  the audit's own persisted `tokenomics.json` artifact (HLD §8.2/§8.3) — read,
  never recomputed, so no pricing golden is owed.
- Determinism: a pure read of DB state + the on-disk artifact; envelopes sort
  on `workspace_ref` (a total key independent of DB scan order), so two
  exports of the same state are byte-identical.
- Engine boundary: this module imports nothing from `services.rules` or
  `services.pricing` (T-NFR-01 spirit) — the engine never learns the word
  "cohort", and this module never learns theirs beyond the plain `FindingRow`
  rows the persistence layer already exposes to every other flywheel module.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, fields
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.persistence.models import Audit, FindingRow, Workspace
from tokenops_cost_auditor.services.dashboard import tokenomics as tokenomics_svc

SCHEMA_VERSION = "1.0"

# Distinct from frame.py's `_HKDF_INFO` (the user-pseudonym context) — a
# workspace_ref and a customer pseudonym must never collide even derived from
# the same SECRET_KEY.
_HKDF_INFO = b"tokenops-flywheel-cohort-workspace"

# The NINE shipped registry ids (services/rules/registry.py DETECTORS): d1-d6,
# d8-d10. d7 never shipped — the LLD's "d1..d10" is span notation, not a
# promise of ten; hardcoded here (not imported) because services/flywheel
# imports no services.rules, ever (T-FLY-07 posture, this module included).
DETECTOR_IDS: tuple[str, ...] = ("d1", "d2", "d3", "d4", "d5", "d6", "d8", "d9", "d10")
_DETECTOR_PREFIX = re.compile(r"^(d\d+)_")

# The five ShapeClass values (services/dashboard/shapes.py, FR-36) — named here
# as plain strings (matching ShapeClass.value) rather than imported, since the
# only shape data this module ever sees is the already-serialized string in
# the persisted tokenomics.json artifact.
SHAPE_KEYS: tuple[str, ...] = (
    "AGENT_LOOP",
    "RETRY_BURST",
    "CONTEXT_GROWTH",
    "UNCLAIMED_CACHE",
    "STEADY",
)

FEATURE_KEYS = frozenset(
    {
        "monthly_spend_usd",
        "tokens_in",
        "tokens_out",
        "tokens_cached",
        "cache_hit_rate",
        "out_in_ratio",
        "detector_fire_rates",
        "shape_mix",
    }
)


def workspace_pseudonym(secret_key: str, workspace_id: str) -> str:
    """Stable, keyed, one-way workspace identity — unrecoverable without
    SECRET_KEY, stable per workspace so the factory can join a workspace's own
    envelopes across periods without ever learning which workspace it is."""
    material = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        secret_key.encode()
    )
    return hmac.new(material, workspace_id.encode(), sha256).hexdigest()


@dataclass(frozen=True)
class CohortExportEnvelope:
    schema_version: str
    period: str
    workspace_ref: str
    k: int
    features: dict[str, object]


@dataclass(frozen=True)
class ExportResult:
    period: str
    k: int  # cohort size: opted-in workspaces with >=1 done audit in the period
    floor: int  # settings.flywheel_l1_min_customers at export time
    envelopes: tuple[CohortExportEnvelope, ...]
    reason: str  # non-empty ONLY when envelopes is empty — names n and the floor


def _detector_fire_rates(session: Session, audit_ids: list[str]) -> dict[str, float]:
    """Fraction of this workspace's period audits that raised >=1 finding for
    each detector id — a rate, never a raw finding count (R-ZTA: no volume
    signal that could fingerprint a specific customer's finding list)."""
    if not audit_ids:
        return dict.fromkeys(DETECTOR_IDS, 0.0)
    fired: dict[str, set[str]] = {d: set() for d in DETECTOR_IDS}
    rows = session.execute(
        select(FindingRow.audit_id, FindingRow.detector).where(FindingRow.audit_id.in_(audit_ids))
    ).all()
    for audit_id, detector in rows:
        m = _DETECTOR_PREFIX.match(detector)
        if m and m.group(1) in fired:
            fired[m.group(1)].add(audit_id)
    n = len(audit_ids)
    return {d: round(len(fired[d]) / n, 4) for d in DETECTOR_IDS}


def _shape_mix(report_dir: str | Path, audit_id: str) -> dict[str, float]:
    """Fraction of the representative audit's classified routes in each
    ShapeClass — a passthrough tally of the persisted `shapes.by_route` block,
    never a recomputation (HLD §8.2/§8.3). Absent/pre-feature artifact -> an
    honest all-zero mix (distinguishable from a real mix, which sums to 1.0).
    Every access type-checked (the routes_dashboard._shape_map cold-gate
    idiom) — a corrupt artifact degrades honestly, never raises."""
    artifact = tokenomics_svc.load_artifact(report_dir, audit_id)
    by_route: list[object] = []
    if isinstance(artifact, dict):
        shapes = artifact.get("shapes")
        if isinstance(shapes, dict):
            entries = shapes.get("by_route")
            if isinstance(entries, list):
                by_route = entries
    if not by_route:
        return dict.fromkeys(SHAPE_KEYS, 0.0)
    counts = dict.fromkeys(SHAPE_KEYS, 0)
    for r in by_route:
        cls = r.get("shape") if isinstance(r, dict) else None
        if cls in counts:
            counts[cls] += 1
    total = len(by_route)
    return {k: round(counts[k] / total, 4) for k in SHAPE_KEYS}


def _vitals(report_dir: str | Path, audit: Audit) -> tuple[float, int, int, int, float, float]:
    """Money/token vitals: a PASSTHROUGH of the audit's own tokenomics.json
    (no recompute drift). A coarse-source/purged/pre-feature audit has no
    artifact — falls back to the audited total_spend_usd and honest zeros for
    the per-request vitals we structurally cannot know without one."""
    artifact = tokenomics_svc.load_artifact(report_dir, audit.id)
    if not isinstance(artifact, dict):
        return round(float(audit.total_spend_usd or 0.0), 2), 0, 0, 0, 0.0, 0.0

    def _num(key: str) -> float:
        v = artifact.get(key, 0.0)
        return float(v) if isinstance(v, int | float) else 0.0

    return (
        round(_num("monthly_spend_usd"), 2),
        int(_num("tokens_in")),
        int(_num("tokens_out")),
        int(_num("tokens_cached")),
        round(_num("cache_hit_rate"), 4),
        round(_num("out_in_ratio"), 4),
    )


def build(session: Session, settings: Settings, period: str) -> ExportResult:
    """The cohort export for one calendar period ("YYYY-MM") — a pure read,
    deterministic given DB state + the on-disk artifacts. Cohort = opted-in
    workspaces with >=1 DONE audit whose (report_ready_at or created_at) falls
    in `period`. k < the L1 floor -> zero envelopes, an honest refusal."""
    floor = settings.flywheel_l1_min_customers
    opted_in_rows = session.execute(
        select(Workspace).where(Workspace.cohort_opt_in.is_(True))
    ).scalars()
    opted_in = {w.id for w in opted_in_rows}
    by_workspace: dict[str, list[Audit]] = {}
    if opted_in:
        for a in session.execute(select(Audit).where(Audit.status == "done")).scalars():
            if a.workspace_id not in opted_in:
                continue
            when = a.report_ready_at or a.created_at
            if f"{when:%Y-%m}" != period:
                continue
            by_workspace.setdefault(a.workspace_id, []).append(a)
    k = len(by_workspace)
    if k < floor:
        return ExportResult(
            period=period,
            k=k,
            floor=floor,
            envelopes=(),
            reason=(
                f"{k} opted-in workspace(s) completed an audit in {period} — the export "
                f"needs at least {floor} (the L1 k-anonymity floor) before any workspace "
                "can be exported without risking re-identification"
            ),
        )
    envelopes: list[CohortExportEnvelope] = []
    for workspace_id, audits in by_workspace.items():
        # Deterministic pick of the representative audit: latest by (when, id) —
        # a total order, never DB scan order (frame.py/benchmarks.py precedent).
        audits.sort(key=lambda a: (a.report_ready_at or a.created_at, a.id))
        latest = audits[-1]
        spend, tin, tout, tcache, chr_, oir = _vitals(settings.report_dir, latest)
        envelopes.append(
            CohortExportEnvelope(
                schema_version=SCHEMA_VERSION,
                period=period,
                workspace_ref=workspace_pseudonym(settings.secret_key, workspace_id),
                k=k,
                features={
                    "monthly_spend_usd": spend,
                    "tokens_in": tin,
                    "tokens_out": tout,
                    "tokens_cached": tcache,
                    "cache_hit_rate": chr_,
                    "out_in_ratio": oir,
                    "detector_fire_rates": _detector_fire_rates(session, [a.id for a in audits]),
                    "shape_mix": _shape_mix(settings.report_dir, latest.id),
                },
            )
        )
    # Total sort key on the EXPORTED identity: the emitted order carries no
    # information about internal db-scan/insertion order (frame.py precedent).
    envelopes.sort(key=lambda e: e.workspace_ref)
    return ExportResult(period=period, k=k, floor=floor, envelopes=tuple(envelopes), reason="")


def envelope_violations(envelope: CohortExportEnvelope) -> list[str]:
    """Executable schema self-audit (T-COH): every field number/enum/id-shaped,
    feature keys pinned exactly — a free-text field cannot ship undetected.
    Returns problems instead of asserting so a failing test names the field."""
    problems: list[str] = []
    declared = tuple(f.name for f in fields(CohortExportEnvelope))
    expected = ("schema_version", "period", "workspace_ref", "k", "features")
    if declared != expected:
        problems.append(f"fields {declared} != {expected}")
    features = envelope.features
    if set(features) != FEATURE_KEYS:
        problems.append(f"feature keys {sorted(features)} != {sorted(FEATURE_KEYS)}")
        return problems
    for key in ("monthly_spend_usd", "cache_hit_rate", "out_in_ratio"):
        if not isinstance(features[key], int | float):
            problems.append(f"{key} not numeric: {features[key]!r}")
    for key in ("tokens_in", "tokens_out", "tokens_cached"):
        if not isinstance(features[key], int):
            problems.append(f"{key} not an int: {features[key]!r}")
    fire = features["detector_fire_rates"]
    if (
        not isinstance(fire, dict)
        or set(fire) != set(DETECTOR_IDS)
        or any(not isinstance(v, int | float) for v in fire.values())
    ):
        problems.append(f"detector_fire_rates keys/values malformed: {fire!r}")
    mix = features["shape_mix"]
    if (
        not isinstance(mix, dict)
        or set(mix) != set(SHAPE_KEYS)
        or any(not isinstance(v, int | float) for v in mix.values())
    ):
        problems.append(f"shape_mix keys/values malformed: {mix!r}")
    return problems
