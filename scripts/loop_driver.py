#!/usr/bin/env python
"""LE-5 — the autonomous issue driver (docs/09-SDLC §6, PLAN-LOOP-ENGINEERING). Picks a
`loop:ready` GitHub Issue and builds it END-TO-END with no human step: an agent (the
pinned `claude` CLI, WRITE-enabled) reads the issue, slices it vertically, implements +
tests + docs, commits under the founder's authorship, pushes, and opens a PR labelled
`auto-merge` — the loop (LE-4 gate round + LE-3 auto-merge + branch protection) then
reviews and ships it. The kill-switch (LE-6 `LOOP_PAUSED`) halts intake; a FAIL from any
gate agent blocks the merge. Prod stays founder-gated (staging-auto only).

`build_prompt`/`select_ready` are pure so the orchestration is unit-tested; `run_agent`
invokes the CLI live. State: `loop:ready` → `loop:in-progress` (this driver) → closed by
the PR's "Closes #N" on merge.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

REPO = "delvinggeeks/tokenops-cost-auditor"
AUTHOR_NAME = "Lokesh Prasanna Kumar S"  # LE-1 authorship law — the ONLY author
READY = "loop:ready"
IN_PROGRESS = "loop:in-progress"
# Read + WRITE + run: the build agent edits files, runs the pinned toolchain, and uses
# git/gh to push and open the PR. (The gate-round agents, by contrast, are read-only.)
_ALLOWED_TOOLS = "Read,Grep,Glob,Bash,Edit,Write"
AGENT_TIMEOUT_S = 3600  # a full slice — implement + test + PR — is a long headless run


def select_ready(issues: list[dict[str, Any]], limit: int = 1) -> list[dict[str, Any]]:
    """The `loop:ready` issues NOT already being built, lowest number first (FIFO), so a
    re-run never double-builds one the driver already claimed (labelled in-progress)."""
    ready = [
        i
        for i in issues
        if READY in {la["name"] for la in i.get("labels", [])}
        and IN_PROGRESS not in {la["name"] for la in i.get("labels", [])}
    ]
    ready.sort(key=lambda i: i.get("number", 0))
    return ready[:limit]


def build_prompt(number: int, title: str, body: str, author_email: str) -> str:
    """The autonomous build agent's instruction. It encodes every CI law that WILL block
    the PR, so the agent works to the same bar a human slice does — the gate round is the
    adversarial catch, not the first line of defence."""
    return (
        "You are the autonomous build agent for the TokenOps Cost Auditor loop (LE-5). "
        f"GitHub Issue #{number} is labelled `loop:ready` — implement it END TO END and "
        "open a PR the loop will merge. Work fully autonomously; there is NO human step.\n\n"
        f"===== ISSUE #{number}: {title} =====\n{body}\n===== end issue =====\n\n"
        "FOLLOW THESE RULES EXACTLY — each is enforced by a CI gate that WILL block your PR:\n"
        "1. Read CLAUDE.md and docs/09-SDLC.md FIRST — they are the build law: scope "
        "freeze X-01..X-05 (no live proxy, no enforcement, no RBAC-over-LLM-traffic, no "
        "LLM narrative in reports, no SPA); FR-22 (never persist prompt/completion text); "
        "the money law; engine boundary T-NFR-01 (services/rules + services/pricing import "
        "zero network/LLM libs).\n"
        "2. VERTICAL SLICE (R-VERTICAL): ship end-to-end in ONE PR — the data/backend "
        "change + its UI surface + the click path that reaches it + a journey/unit test "
        "walking it + honest empty/error states. A layer without its reachable surface "
        "does NOT merge.\n"
        "3. Branch off `main` (name it for the issue). Implement. Add tests per "
        "docs/05-TEST-PLAN patterns. Update docs/04-TRACEABILITY.md in the SAME commit if "
        "you implement a requirement; regenerate docs-site/api/endpoints.md "
        "(`uv run python scripts/export_openapi.py`) if you add or change a route.\n"
        "4. Make the PINNED toolchain GREEN before pushing — nothing else is valid (TE-11):\n"
        "   uv run ruff check . && uv run ruff format . && uv run mypy "
        "&& uv run pytest -m 'not perf'\n"
        "5. AUTHORSHIP LAW (LE-1, CI-enforced, NON-NEGOTIABLE): every commit is authored by "
        f'"{AUTHOR_NAME}" with NO co-author trailer and NO AI reference ANYWHERE in the '
        "commit message/body. Run first:\n"
        f'   git config user.name "{AUTHOR_NAME}" && git config user.email "{author_email}"\n'
        "   Write conventional-commit messages (feat/fix/docs/test...). A single AI trailer "
        "FAILS the build.\n"
        "6. Push the branch. Open the PR with `gh pr create`; its body MUST end with "
        f'"Closes #{number}" (so merging closes the issue). Then label the PR `auto-merge` '
        "(`gh pr edit <pr> --add-label auto-merge`). The loop reviews (gate round) and "
        "merges it — you do NOT merge it yourself, and you never use --admin.\n"
        "7. If you CANNOT complete the slice to a green toolchain, do NOT open a half-PR: "
        f"comment on issue #{number} explaining exactly what blocked you, and stop.\n\n"
        "STAY IN SCOPE: implement ONLY what the issue asks. A new idea you notice goes to "
        "docs/internal/BACKLOG.md as one line, never into code (scope freeze)."
    )


def _gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)


def run_agent(number: int, title: str, body: str, author_email: str, dry_run: bool) -> str:
    """Invoke the pinned claude CLI as the WRITE-enabled build agent over the issue.
    dry_run returns the prompt (for tests/inspection) without spending a run."""
    prompt = build_prompt(number, title, body, author_email)
    if dry_run:
        return prompt
    proc = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", _ALLOWED_TOOLS, "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=AGENT_TIMEOUT_S,
        check=False,
    )
    return proc.stdout + ("\n" + proc.stderr if proc.returncode != 0 else "")


def main() -> int:
    import json

    author_email = sys.argv[1] if len(sys.argv) > 1 else "delving.geeks@gmail.com"
    issues = json.loads(
        _gh(
            [
                "issue",
                "list",
                "--repo",
                REPO,
                "--label",
                READY,
                "--state",
                "open",
                "--json",
                "number,title,body,labels",
                "--limit",
                "50",
            ]
        ).stdout
        or "[]"
    )
    ready = select_ready(issues)
    if not ready:
        print("loop-driver: no loop:ready issues to build")
        return 0
    issue = ready[0]
    n = issue["number"]
    print(f"loop-driver: building issue #{n} — {issue['title']}")
    _gh(["issue", "edit", str(n), "--repo", REPO, "--add-label", IN_PROGRESS])
    out = run_agent(n, issue["title"], issue.get("body") or "", author_email, dry_run=False)
    print(out[-4000:])
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
