"""T-D1 — docs-drift tests for docs/internal/CODE-TOUR.md (mirrors the
test_docs_site.py idiom). CODE-TOUR.md is read by a technical founder who did
not write the code (WP-COMPREHEND); every fact it states about the tree must
stay true, or the tour teaches something that no longer exists. This suite
is why the six-detector / 8-table / hand-verified-pricing drift this card
fixed can't silently recur.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parents[1]
TOUR = REPO / "docs/internal/CODE-TOUR.md"
TOUR_TEXT = TOUR.read_text(encoding="utf-8")

_SKIP_DIR_PARTS = {".git", ".venv", "node_modules", "__pycache__"}

_NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}


def _all_repo_paths() -> set[str]:
    paths = set()
    for p in REPO.rglob("*"):
        if any(part in _SKIP_DIR_PARTS for part in p.parts):
            continue
        paths.add(p.relative_to(REPO).as_posix())
    return paths


def _backticked_tokens() -> list[str]:
    return re.findall(r"`([^`\n]+)`", TOUR_TEXT)


def _looks_like_path(token: str) -> bool:
    """A backtick token is a repo path when it's whitespace-free and has a
    '/' — that excludes prose words, HTTP routes ('POST /razorpay/order'
    has a space), and symbol calls (no '/' in a bare function name)."""
    return "/" in token and not any(c.isspace() for c in token)


def _path_exists(token: str, all_paths: set[str]) -> bool:
    """Exact match from repo root, or a suffix match against every real repo
    path — CODE-TOUR often shortens `src/tokenops_cost_auditor/mcp/server.py`
    to `mcp/server.py` in prose, which is still an unambiguous real file."""
    token = token.rstrip("/")
    if (REPO / token).exists():
        return True
    return any(p == token or p.endswith("/" + token) for p in all_paths)


def _extract_symbol(token: str) -> str | None:
    """`AuditRunner.run()` -> run; `findings.py::effective_prompt_rate()` ->
    effective_prompt_rate; `create_audit()` -> create_audit. None for a
    backtick token that isn't a function/method call at all."""
    if "(" not in token:
        return None
    head = token.split("(", 1)[0]
    if "::" in head:
        head = head.split("::")[-1]
    if "." in head:
        head = head.rsplit(".", 1)[-1]
    return head or None


def _all_src_def_names() -> set[str]:
    names = set()
    def_re = re.compile(r"^\s*def\s+(\w+)\s*\(", flags=re.MULTILINE)
    for p in (REPO / "src").rglob("*.py"):
        for m in def_re.finditer(p.read_text(encoding="utf-8")):
            names.add(m.group(1))
    return names


class TestCodeTourPaths:
    """Every backticked repo path the tour points a reader to must exist."""

    def test_every_backticked_path_exists_on_disk(self) -> None:
        all_paths = _all_repo_paths()
        tokens = [t for t in _backticked_tokens() if _looks_like_path(t)]
        missing = [t for t in tokens if not _path_exists(t, all_paths)]
        assert not missing, f"CODE-TOUR.md points at paths that don't exist: {missing}"

    def test_non_vacuous(self) -> None:
        """Guard against the check above silently matching nothing if the
        tour's formatting ever changes (e.g. stops moving to code fences)."""
        path_tokens = [t for t in _backticked_tokens() if _looks_like_path(t)]
        assert len(path_tokens) >= 20, (
            f"only found {len(path_tokens)} path-like backtick tokens — "
            "the path-existence guard may be inspecting the wrong markup"
        )


class TestCodeTourSymbols:
    """Every backticked `symbol()` the tour names as a 'read first' function
    must resolve to a real `def` somewhere under src/."""

    def test_every_backticked_call_resolves_to_a_def(self) -> None:
        def_names = _all_src_def_names()
        symbols = {_extract_symbol(t) for t in _backticked_tokens()}
        symbols.discard(None)
        missing = sorted(s for s in symbols if s not in def_names)
        assert not missing, (
            f"CODE-TOUR.md names function(s) with no matching def under src/: {missing}"
        )

    def test_non_vacuous(self) -> None:
        symbols = {_extract_symbol(t) for t in _backticked_tokens()}
        symbols.discard(None)
        assert len(symbols) >= 10, (
            f"only found {len(symbols)} symbol-call backtick tokens — "
            "the symbol-resolution guard may be inspecting the wrong markup"
        )


class TestCodeTourDetectorCount:
    """Stop 4's detector count must derive from the shipped registry, not a
    hand-typed number — a d11 landing without a tour touch must fail this."""

    def test_detector_count_word_matches_registry(self) -> None:
        from tokenops_cost_auditor.services.rules.registry import DETECTORS

        n = len(DETECTORS)
        word = _NUMBER_WORDS[n]
        assert f"{word} detectors" in TOUR_TEXT.lower(), (
            f"registry ships {n} detectors ('{word}') but CODE-TOUR.md's Stop 4 "
            "doesn't say so — refresh the tour in the same commit as a detector change"
        )

    def test_detector_span_bounds_and_skip_gap_stated(self) -> None:
        """The registry's lowest/highest short ids (d1, d10, ...) must be
        named as the span, and any never-shipped id inside that span (d7)
        must be named as skipped so a reader isn't left hunting for a file
        that isn't there."""
        from tokenops_cost_auditor.services.rules.registry import DETECTORS

        shipped_ids = {d.name.split("_", 1)[0] for d in DETECTORS}
        max_n = max(int(i[1:]) for i in shipped_ids)
        full_span = {f"d{i}" for i in range(1, max_n + 1)}
        skipped_ids = full_span - shipped_ids

        assert "d1" in TOUR_TEXT and f"d{max_n}" in TOUR_TEXT, (
            f"CODE-TOUR.md's Stop 4 must name the detector id span (d1..d{max_n})"
        )
        for did in skipped_ids:
            assert did in TOUR_TEXT, (
                f"detector id {did!r} was never shipped inside the d1-d{max_n} span but "
                "CODE-TOUR.md doesn't call out the gap"
            )
