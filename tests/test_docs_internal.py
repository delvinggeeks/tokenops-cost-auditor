"""T-D1 tests — docs-drift tripwire for docs/internal/CODE-TOUR.md.

CODE-TOUR.md is the WP-COMPREHEND reading guide: a founder walks it top to
bottom and trusts every path, symbol, and detector count it cites. These
tests fail the moment the tour drifts from the code it describes — a moved
file, a renamed function, a shipped detector the tour never mentions, or a
stale counted-detector claim ("six detectors" at nine) creeping back into
src/ code, templates, scripts, or help copy. They do NOT check docs-site/
(that is T-D4's scope — including its own six-detector-era copy).
"""

import re
from pathlib import Path

REPO = Path(__file__).parents[1]
CODE_TOUR = REPO / "docs/internal/CODE-TOUR.md"
SRC = REPO / "src/tokenops_cost_auditor"

PATH_TOKEN_RE = re.compile(r"`([^`]+)`")
SYMBOL_CALL_RE = re.compile(r"`([A-Za-z_][\w.]*)\(\)`")
DETECTOR_COUNT_RE = re.compile(r"the (\w+) detectors")
# ANY spelled count beside "detector" goes stale the moment a detector ships
# (the T-D1 system-tester FAIL: six customer surfaces said "six" at nine).
COUNTED_DETECTOR_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)[- ]detector",
    re.IGNORECASE,
)
# Customer-facing copy lives in templates/scripts/yaml, not only .py docstrings.
SRC_COPY_GLOBS = ("*.py", "*.html", "*.js", "*.yaml", "*.yml")

DETECTOR_COUNT_WORDS = {
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


# The tour cites paths at three depths: repo-relative (src/..., docs/...),
# package-relative (web/..., api/...), and stop-context-relative inside the
# services/persistence stops (payments/base.py, migrations/). A citation
# counts as existing if ANY base resolves it; a moved file fails at every
# base. No prefix allowlist — an allowlist silently exempts whatever citation
# form it forgot (the V-T-D1 cold-review note).
PATH_BASES = (
    "",
    "src/tokenops_cost_auditor",
    "src/tokenops_cost_auditor/services",
    "src/tokenops_cost_auditor/persistence",
)


def _split_citation(token: str) -> tuple[str, str | None]:
    """`path::symbol()` → (path, symbol); plain tokens → (token, None).
    The split runs BEFORE the path filter — the raw token ends in `()`, so
    filtering on it would skip the whole citation (round-3 gate note)."""
    if "::" in token:
        path, _, sym = token.partition("::")
        call = re.fullmatch(r"([A-Za-z_][\w.]*)\(\)", sym)
        return path, call.group(1).split(".")[-1] if call else None
    return token, None


def _cited_repo_paths(text: str) -> list[str]:
    paths = []
    for token in PATH_TOKEN_RE.findall(text):
        rel, _ = _split_citation(token)
        if rel == "docker-compose.yml" or (
            " " not in rel
            and "://" not in rel  # URLs of any scheme are not repo paths
            and not rel.startswith("http")
            and not rel.startswith("/")  # `/developer` etc. are product ROUTES, not repo paths
            and ("/" in rel or rel.endswith(".py"))  # bare `subscriptions.py` cites a file too
        ):
            paths.append(rel)
    return paths


def _resolves(rel: str) -> bool:
    rel = rel.rstrip("/")
    if any((REPO / base / rel).exists() for base in PATH_BASES):
        return True
    # A bare filename is cited from inside its stop's module context (Stop 9
    # says `subscriptions.py` meaning services/payments/) — it exists if it
    # lives anywhere under the package.
    return "/" not in rel and any(SRC.rglob(rel))


def _cited_symbol_pairs(text: str) -> list[tuple[str | None, str]]:
    """(file, symbol) pairs. Bare `name()` tokens pair with None and are
    checked against the whole package; `path::symbol()` citations name their
    file, so the symbol must be defined IN THAT FILE — compute()/build()
    exist in several modules, and a corpus-wide check would keep passing
    after a mis-pairing or a rename (round-5 gate note)."""
    pairs: list[tuple[str | None, str]] = [
        (None, call.split(".")[-1]) for call in SYMBOL_CALL_RE.findall(text)
    ]
    for token in PATH_TOKEN_RE.findall(text):
        rel, sym = _split_citation(token)
        if sym is not None:
            pairs.append((rel, sym))
    return pairs


def _cited_file(rel: str) -> Path | None:
    for base in PATH_BASES:
        if (REPO / base / rel).is_file():
            return REPO / base / rel
    if "/" not in rel:
        return next(iter(SRC.rglob(rel)), None)
    return None


class TestCodeTourDrift:
    def test_every_cited_repo_path_exists(self) -> None:
        text = CODE_TOUR.read_text(encoding="utf-8")
        missing = [t for t in _cited_repo_paths(text) if not _resolves(t)]
        assert not missing, f"CODE-TOUR.md cites repo paths that do not exist: {missing}"

    def test_every_cited_symbol_resolves(self) -> None:
        text = CODE_TOUR.read_text(encoding="utf-8")
        corpus = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.py"))
        missing = []
        for rel, name in sorted(set(_cited_symbol_pairs(text)), key=str):
            if rel is None:
                if f"def {name}(" not in corpus:
                    missing.append(name)
                continue
            target = _cited_file(rel)
            if target is None or f"def {name}(" not in target.read_text(encoding="utf-8"):
                missing.append(f"{rel}::{name}")
        assert not missing, (
            f"CODE-TOUR.md cites symbols with no matching `def` in the cited "
            f"file (or package, for bare names): {missing}"
        )

    def test_detector_count_word_matches_registry(self) -> None:
        """A detector shipping (d11, d12, ...) without CODE-TOUR.md's "the
        <word> detectors" line being touched fails this test: the word and
        the registry length are asserted equal, so the tour update is not
        optional decoration — it is part of the detector's DoD.
        """
        text = CODE_TOUR.read_text(encoding="utf-8")
        match = DETECTOR_COUNT_RE.search(text)
        assert match is not None, "CODE-TOUR.md no longer contains a 'the <word> detectors' claim"
        word = match.group(1)
        assert word in DETECTOR_COUNT_WORDS, (
            f"CODE-TOUR.md detector-count word {word!r} has no number mapping"
        )

        from tokenops_cost_auditor.services.rules.registry import DETECTORS

        assert DETECTOR_COUNT_WORDS[word] == len(DETECTORS), (
            f"CODE-TOUR.md says 'the {word} detectors' "
            f"({DETECTOR_COUNT_WORDS[word]}) but registry.DETECTORS has "
            f"{len(DETECTORS)} entries — a detector shipped or was removed "
            "without the tour being updated"
        )


class TestCountFreeDetectorClaims:
    def test_no_literal_counted_detector_claims_in_src(self) -> None:
        """No file under src/ — code, template, script, or help copy — may
        hard-code a "<count> detectors" figure: it goes stale every time a
        detector ships. The T-D1 gate round proved the .py-only version of
        this check gave false confidence while findings.html, landing.html,
        tour.js and help_registry.yaml told customers "six" at nine.
        """
        offenders = [
            f"{path.relative_to(REPO)}: {m.group(0)!r}"
            for glob in SRC_COPY_GLOBS
            for path in sorted(SRC.rglob(glob))
            if (m := COUNTED_DETECTOR_RE.search(path.read_text(encoding="utf-8")))
        ]
        assert not offenders, f"stale counted-detector claim(s) found in: {offenders}"
