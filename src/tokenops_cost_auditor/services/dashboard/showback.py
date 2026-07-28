"""Showback CSV (FR-38): the finance-grade allocation export.

Serializes the tokenomics.json artifact an audit already wrote into the
LLD §9.5 CSV — ``dimension,name,calls,monthly_usd,share,pct_attributed_caveat``
— one row per ``by_model`` slice (dimension=model) and per ``by_route`` slice
(dimension=route), in the artifact's own monthly-$ ranking order. Route IS the
tag allocation (``by_route`` groups by the call ``tag``); FR-38's
"tag/route/model" names that provenance, not a third grouping.

Byte-for-byte discipline (FR-38 Accept): figures are the ARTIFACT's values
serialized with Python's shortest-roundtrip float repr — the same bytes
``json.dumps`` wrote into the artifact — never recomputed, never re-rounded.
The page rounds for reading; the file must reconcile to the tokenomics
goldens exactly.

The attribution caveat (spend-weighted coverage, fixed template) rides on
EVERY row so the honesty survives the handoff into a spreadsheet. An empty
allocation degrades to the header + one ``#`` comment line (LLD §9.5), never
an empty grid that reads as a broken export.

FR-22 by construction: the artifact holds dimension names, counts and
dollars only — there is no prompt/completion text to leak.
"""

from __future__ import annotations

import csv
import io

HEADER = ("dimension", "name", "calls", "monthly_usd", "share", "pct_attributed_caveat")
EMPTY_COMMENT = "# nothing to allocate — none of this audit's requests could be priced"


def _caveat(pct_attributed: float) -> str:
    """Fixed template; the percentage prints exactly as the page's coverage stat
    (``{:.0f}%``) so the file and the page never disagree on the printed figure."""
    return f"{pct_attributed * 100:.0f}% of spend carries a route tag"


def render_csv(artifact: dict[str, object]) -> str:
    """The tokenomics artifact dict (``tokenomics.load_artifact``) as showback CSV."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")  # RFC 4180 line endings
    writer.writerow(HEADER)
    by_model = artifact.get("by_model") or ()
    by_route = artifact.get("by_route") or ()
    if not by_model and not by_route:
        out.write(EMPTY_COMMENT + "\r\n")
        return out.getvalue()
    caveat = _caveat(float(artifact.get("pct_attributed", 0.0)))  # type: ignore[arg-type]
    for dimension, slices in (("model", by_model), ("route", by_route)):
        for s in slices:  # type: ignore[attr-defined]
            writer.writerow(
                (dimension, s["name"], s["calls"], s["monthly_usd"], s["share"], caveat)
            )
    return out.getvalue()
