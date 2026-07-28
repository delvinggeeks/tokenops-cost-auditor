"""Deterministic tokenomics breakdown (founder 2026-07-25, enterprise depth engine).

Pure arithmetic over a PRICED frame (cost_usd present): every figure is a sum or
ratio of already-priced, observed token counts — exact, reproducible, no model,
no estimate. This is the enterprise FinOps-for-AI breakdown: vitals, per-dimension
slices (model / route), unit economics, and data-coverage — the audit-grade
numbers a finance team can reconcile to the penny, which an LLM cannot produce.

Not a new pricing estimator (it only aggregates cost_usd the coster already
computed), so no rate golden is owed — but the money is pinned by test_tokenomics
against hand-derived values. Engine-pure: no network/LLM (T-NFR-01 spirit).

Also computes the behaviour lens (FR-36): one `shapes.ShapeResult` per route,
keyed by the same route name as `by_route` — the deterministic workload-shape
classification riding alongside the dollar breakdown so both surfaces (the
`/breakdown` page and the read API) agree on what shape a route is.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from tokenops_cost_auditor.config import Settings, get_settings
from tokenops_cost_auditor.services.dashboard import shapes
from tokenops_cost_auditor.services.rules.findings import monthly_factor, observed_days

UNTAGGED = "(untagged)"


@dataclass(frozen=True)
class Slice:
    """One dimension value (a model, or a route/tag) with its exact economics."""

    name: str
    calls: int
    monthly_usd: float
    share: float  # fraction of total priced spend
    cache_hit_rate: float  # cached_tokens / input_tokens
    out_in_ratio: float  # completion_tokens / input_tokens
    cost_per_1k_out: float


@dataclass(frozen=True)
class Tokenomics:
    monthly_spend_usd: float
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    cache_hit_rate: float
    out_in_ratio: float
    cost_per_1k_out: float
    cost_per_request: float
    by_model: tuple[Slice, ...]
    by_route: tuple[Slice, ...]
    pct_priced: float  # share of REQUESTS we could price (unpriced $ is unknowable)
    pct_attributed: float  # share of SPEND (dollars) carrying a route tag
    # FR-36 behaviour lens: one shape per route, keyed by the same name as
    # by_route. Additive — an older/pre-feature artifact simply lacks this key
    # (honest null downstream, never a fabricated shape).
    route_shapes: dict[str, shapes.ShapeResult]


def _rate(numer: float, denom: float) -> float:
    return numer / denom if denom > 0 else 0.0


def _slice(name: str, group: pd.DataFrame, total_cost: float, factor: float) -> Slice:
    cost = float(group["cost_usd"].sum())
    inp = int(group["prompt_tokens"].sum())
    out = int(group["completion_tokens"].sum())
    cached = int(group["cached_tokens"].sum())
    return Slice(
        name=name,
        calls=len(group),
        monthly_usd=cost * factor,
        share=_rate(cost, total_cost),
        cache_hit_rate=_rate(cached, inp),
        out_in_ratio=_rate(out, inp),
        cost_per_1k_out=_rate(cost, out / 1000.0),
    )


def _route_name(tag: object) -> str:
    return str(tag) if str(tag).strip() else UNTAGGED


def _ranked(
    rows: pd.DataFrame,
    col: str,
    name: Callable[[object], str],
    total_cost: float,
    factor: float,
) -> tuple[Slice, ...]:
    """Slices over a grouping column, named by `name(value)`, ranked by monthly $."""
    out = [_slice(name(v), g, total_cost, factor) for v, g in rows.groupby(col, sort=True)]
    return tuple(sorted(out, key=lambda s: -s.monthly_usd))


def _route_shapes(rows: pd.DataFrame, settings: Settings) -> dict[str, shapes.ShapeResult]:
    return {
        _route_name(tag): shapes.classify(group, settings)
        for tag, group in rows.groupby("tag", sort=True)
    }


def compute(priced: pd.DataFrame, settings: Settings | None = None) -> Tokenomics:
    """The exact tokenomics breakdown for one audited frame. Unpriced rows (NaN
    cost) are excluded from money/ratios but counted in pct_priced, so the
    coverage is honest and the dollars reconcile to what we could actually price."""
    settings = settings if settings is not None else get_settings()
    n_total = len(priced)
    if n_total == 0:
        return Tokenomics(0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, (), (), 0.0, 0.0, {})
    rows = priced.dropna(subset=["cost_usd"])
    total_cost = float(rows["cost_usd"].sum()) if len(rows) else 0.0
    factor = monthly_factor(observed_days(priced))
    inp = int(rows["prompt_tokens"].sum()) if len(rows) else 0
    out = int(rows["completion_tokens"].sum()) if len(rows) else 0
    cached = int(rows["cached_tokens"].sum()) if len(rows) else 0

    by_model = _ranked(rows, "model", str, total_cost, factor)
    by_route = _ranked(rows, "tag", _route_name, total_cost, factor)
    route_shapes = _route_shapes(rows, settings) if len(rows) else {}
    # Attribution is SPEND-weighted (cold gate): what share of DOLLARS carries a
    # route tag — a cheap untagged call matters less than an expensive one.
    if len(rows):
        tagged_cost = float(rows.loc[rows["tag"].astype(str).str.strip() != "", "cost_usd"].sum())
    else:
        tagged_cost = 0.0
    return Tokenomics(
        monthly_spend_usd=total_cost * factor,
        tokens_in=inp,
        tokens_out=out,
        tokens_cached=cached,
        cache_hit_rate=_rate(cached, inp),
        out_in_ratio=_rate(out, inp),
        cost_per_1k_out=_rate(total_cost, out / 1000.0),
        route_shapes=route_shapes,
        cost_per_request=_rate(total_cost, n_total),
        by_model=by_model,
        by_route=by_route,
        pct_priced=_rate(len(rows), n_total),  # share of REQUESTS we could price
        pct_attributed=_rate(tagged_cost, total_cost),  # share of SPEND carrying a tag
    )


def load_artifact(report_dir: str | Path, audit_id: str) -> dict[str, object] | None:
    """The exact tokenomics.json the runner wrote for an audit, or None when it is
    absent/corrupt/purged (FR-21) — honest empty state, never a raise. Shared by
    the HTML `/breakdown` page and the read API so both surfaces agree on when a
    breakdown "exists" (single loader, no drift)."""
    path = Path(report_dir) / audit_id / "tokenomics.json"
    if not path.exists():
        return None
    try:
        data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except json.JSONDecodeError, OSError:
        return None
