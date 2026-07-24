#!/usr/bin/env python3
"""Authorship guard — a HARD gate (CLAUDE.md rule 6; founder 2026-07-24 reaffirm:
"Author is Lokesh Prasanna Kumar S and no traces of AI co-author headers or
footers in any repo").

Every commit in the range must be authored by the founder and carry NO AI trace:
no `Co-Authored-By` trailer, no `Claude`/`Anthropic`/robot-emoji reference in the
message, no anthropic author address. This is enforcement, not discipline, so it
holds for AUTOMATED / loop-engineering commits too — the no-human-gate merge loop
can only be trusted if authorship is provably clean at the gate.

Usage:
    python scripts/check_authorship.py [<git-range>]

Default range is `origin/main..HEAD` (a PR's own commits); falls back to every
commit when no baseline exists (a fresh repo). Exits 1 listing every offender.
"""

from __future__ import annotations

import re
import subprocess
import sys

AUTHOR_NAME = "Lokesh Prasanna Kumar S"

# Targets the STRUCTURE of an AI attribution header/footer, not bare word
# mentions — so honest prose (this repo's own docs quote the assistant names
# constantly) never trips it. Matches: a `Co-Authored-By:` trailer LINE, the
# robot-emoji "Generated with" footer, and the AI co-author address.
FORBIDDEN = re.compile(
    r"(?im)^\s*co-authored-by\s*:"  # the co-author trailer line
    r"|🤖"  # robot-emoji footer marker
    r"|generated with \[?claude"  # "Generated with [Claude Code]" footer
    r"|noreply@anthropic",  # the AI co-author email address
)


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def _commits(rng: str) -> list[str]:
    return [c for c in _run(["git", "rev-list", rng]).split() if c]


def _field(sha: str, fmt: str) -> str:
    return _run(["git", "show", "-s", f"--format={fmt}", sha])


def main() -> int:
    rng = sys.argv[1] if len(sys.argv) > 1 else "origin/main..HEAD"
    try:
        shas = _commits(rng)
    except subprocess.CalledProcessError:
        # no such baseline (e.g. a fresh repo with no origin/main) — check all
        shas = _commits("HEAD")

    violations: list[tuple[str, str]] = []
    for sha in shas:
        name = _field(sha, "%an").strip()
        email = _field(sha, "%ae").strip()
        cemail = _field(sha, "%ce").strip()
        body = _field(sha, "%B")
        problems: list[str] = []
        if name != AUTHOR_NAME:
            problems.append(f"author '{name}' != '{AUTHOR_NAME}'")
        if "anthropic" in email.lower() or "anthropic" in cemail.lower():
            problems.append("commit carries an AI (anthropic) email address")
        hit = FORBIDDEN.search(body)
        if hit:
            problems.append(f"AI trace in message: '{hit.group(0)}'")
        if problems:
            violations.append((sha[:10], "; ".join(problems)))

    if violations:
        print("AUTHORSHIP GUARD: FAIL — clean-authorship law violated (CLAUDE.md rule 6):")
        for sha, why in violations:
            print(f"  {sha}  {why}")
        print(
            "\nFix: rewrite the offending commit(s) so the author is "
            f"'{AUTHOR_NAME}' with no AI trailer/reference, then re-push."
        )
        return 1

    print(f"AUTHORSHIP GUARD: OK — {len(shas)} commit(s) checked, all clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
