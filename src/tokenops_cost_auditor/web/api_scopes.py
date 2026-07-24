"""Read-API scopes (S-6, R-SDK-PLATFORM).

The platform's READ half exposes exactly two scopes today. Both are READ —
there is deliberately no write scope here: writing usage stays the write-only
ingest-key (ik_) path, so a read token or an OAuth grant can never mutate an
account. Personal API tokens (rt_) and OAuth access tokens (at_) both draw
their authority from this same closed set.

X-01/X-02 unaffected: a scope governs who may READ our product data, never the
customer's LLM traffic. The audit engine stays tenant-blind; scope lives here
at the web boundary.
"""

from __future__ import annotations

# slug -> human sentence shown on the consent screen and Developer Settings.
READ_SCOPES: dict[str, str] = {
    "read:audits": "See your audits — their status, spend totals, and counts.",
    "read:findings": "See the findings inside an audit — detector, severity, and dollar impact.",
}


def parse_scopes(raw: str) -> list[str]:
    """A stored CSV / a space- or comma-separated request param -> known scopes,
    de-duplicated, order-stable, unknown tokens dropped."""
    seen: dict[str, None] = {}
    for chunk in raw.replace(",", " ").split():
        if chunk in READ_SCOPES:
            seen.setdefault(chunk, None)
    return list(seen)


def scopes_are_known(raw: str) -> bool:
    """True only if every requested token is a real read scope AND at least one
    was asked for. An unknown scope is rejected loudly, never silently dropped."""
    tokens = [c for c in raw.replace(",", " ").split() if c]
    return bool(tokens) and all(t in READ_SCOPES for t in tokens)


def is_subset(requested: str, ceiling: str) -> bool:
    """Every requested scope must sit within the ceiling (the app's registered
    scopes, or a token's granted scopes)."""
    return set(parse_scopes(requested)).issubset(set(parse_scopes(ceiling)))


def to_csv(scopes: list[str]) -> str:
    """Canonical stored form: space-free, order preserved, known-only."""
    return " ".join(s for s in scopes if s in READ_SCOPES)
