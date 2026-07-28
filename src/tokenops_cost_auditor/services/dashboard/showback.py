"""Showback CSV export (FR-38, LLD §9.5) — the finance-grade download beside
the tokenomics math it serializes (services/dashboard/tokenomics.py). Every
figure is read VERBATIM from the tokenomics.json artifact — no
recomputation, no re-rounding — so the export always agrees with the
`/breakdown` page and the tokenomics goldens byte-for-byte. Pure stdlib
csv/string building — no new deps; engine untouched (T-NFR-01 unaffected).
"""

from __future__ import annotations

import csv
import io

HEADER = ("dimension", "name", "calls", "monthly_usd", "share", "pct_attributed_caveat")

# LLD §9.5: an empty allocation degrades to the header row + this honest
# comment line — never a fabricated zero-row table.
_EMPTY_COMMENT = "# no priced spend in this audit -- nothing to allocate"


def _caveat(pct_attributed: object) -> str:
    pct = pct_attributed if isinstance(pct_attributed, (int, float)) else 0.0
    return f"{pct * 100:.0f}% of spend carries a route tag"


def _slices(artifact: dict[str, object], key: str) -> list[dict[str, object]]:
    value = artifact.get(key)
    if not isinstance(value, list):
        return []
    return [s for s in value if isinstance(s, dict)]


def to_csv(artifact: dict[str, object]) -> str:
    """The showback CSV for one tokenomics artifact dict (as returned by
    `tokenomics.load_artifact`). One row per `by_model` slice
    (dimension=model) and per `by_route` slice (dimension=route), figures
    taken verbatim from the artifact. Every row carries the same
    spend-attribution caveat, derived from the artifact's `pct_attributed`."""
    by_model = _slices(artifact, "by_model")
    by_route = _slices(artifact, "by_route")
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(HEADER)
    if not by_model and not by_route:
        buf.write(_EMPTY_COMMENT + "\r\n")
        return buf.getvalue()
    caveat = _caveat(artifact.get("pct_attributed"))
    for dimension, slices in (("model", by_model), ("route", by_route)):
        for s in slices:
            writer.writerow(
                [
                    dimension,
                    s.get("name"),
                    s.get("calls"),
                    s.get("monthly_usd"),
                    s.get("share"),
                    caveat,
                ]
            )
    return buf.getvalue()
