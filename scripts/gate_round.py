#!/usr/bin/env python
"""LE-4 — the adversarial gate round, run HEADLESS in CI (docs/09-SDLC §4/§6).

The keystone of loop engineering: the gate agents that today are run BY HAND in the
main thread are run here against the PR diff, each emits its TE-8 verdict, and the
process exits non-zero if ANY returns FAIL — so a PR cannot pass the gate check on a
FAIL verdict without a human. This turns "gated by discipline" into "gated by machine."

Mechanism: for each required gate it invokes the pinned `claude` CLI headless
(`claude -p --model sonnet ...`) with that agent's charter (`.claude/agents/<name>.md`)
+ the PR diff, captures the TE-8 verdict, and aggregates. Each gate runs on the model
named in its charter (all `sonnet` — TE-5 cost tiering), never the runner's default.

Auth in CI needs a credential (a GitHub runner has no logged-in session): EITHER
CLAUDE_CODE_OAUTH_TOKEN (runs on the founder's Claude SUBSCRIPTION — no metered API
bill, the cheaper lane) OR ANTHROPIC_API_KEY (metered API). The CLI picks up whichever
is set; the workflow accepts either.

Testable without the API: `--dry-run` mocks each agent's output so the harness's own
logic — gate selection, diff capture, verdict parsing, aggregation, exit code, PR
comment — is exercised in CI and unit tests. LIVE behaviour (a real agent call) needs
the key + one validation run on a throwaway PR before this check is made required.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Gates that run on EVERY card (docs/09-SDLC §4). ux-reviewer is added when the diff
# touches a customer-facing surface; architect/ops when it touches structure/infra.
CORE_GATES = ("cold-reviewer", "spec-guard", "vv-engineer", "system-tester")
UX_TRIGGER = ("web/templates/", "web/static/", "templates/app/", "landing")
# docs/uml/ is the architect's own artifact surface (its charter verifies package
# boundaries AND emits/verifies the Mermaid set) — a diagram-only diff must draw the
# architect gate or a "D6/D13-style pass" card ships reviewed by no one (T-D2 gap).
ARCHITECT_TRIGGER = ("services/", "persistence/models.py", "docs/uml/")
# Specific tokens, not bare "docker"/"compose" — the latter also match docs/
# dockerized-notes.md and decompose.py, drawing an unneeded ops gate (cold-reviewer note).
OPS_TRIGGER = (
    ".github/workflows/",
    "scripts/provision",
    "Dockerfile",
    "docker-compose",
    "compose.yml",
    "compose.yaml",
    "Caddyfile",
)

AGENTS_DIR = Path(".claude/agents")
DIFF_CAP = 200_000  # chars of diff embedded in the prompt (kept under model context)
# Per-agent wall-clock backstop. Raised from 900s after O-2 (PR #26) timed vv out to
# NO-VERDICT: the primary fix is telling agents NOT to re-run the full suite (below),
# this ceiling is the safety margin so a legitimately thorough gate still concludes.
AGENT_TIMEOUT_S = 1200
# In-process attempts before a verdict-only reply becomes NO-VERDICT. Three, not two:
# two was empirically not enough — one agent burned five consecutive ROUNDS on the same
# diff, each costing a human-initiated re-run, while its peers reviewed that diff fine.
# The harness already knows the remedy is "re-run", so it should perform it (LE-12).
ATTEMPTS_ON_TRUNCATION = 3
# TE-8: "VERDICT (PASS | PASS-WITH-NOTES | FAIL)". Longest label first so PASS-WITH-NOTES
# is never shadowed by a bare PASS match; trailing \b so "PASSED"/"FAILING" don't parse as
# a clean verdict (the label must stand as a whole word).
_VERDICT_RE = re.compile(r"VERDICT\W{0,4}(PASS-WITH-NOTES|PASS|FAIL)\b", re.IGNORECASE)


@dataclass(frozen=True)
class GateResult:
    agent: str
    verdict: str  # PASS | PASS-WITH-NOTES | FAIL | NO-VERDICT
    output: str


def parse_verdict(text: str) -> str:
    """Extract the TE-8 verdict from an agent's output; NO-VERDICT if none is emitted
    (treated as a failure — a gate that did not conclude did not pass).

    Takes the LAST match, not the first: TE-8 puts the verdict on the FINAL line, and a
    verbose agent commonly echoes the instruction's own "VERDICT: PASS | ... | FAIL"
    example earlier in its reasoning — first-match would lock onto that echo and could
    report a false PASS over a real FAIL (cold-reviewer finding)."""
    matches = list(_VERDICT_RE.finditer(text or ""))
    if not matches:
        return "NO-VERDICT"
    return matches[-1].group(1).upper().replace(" ", "-")


def _changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def select_gates(changed: list[str]) -> list[str]:
    """The gate set for THIS diff (docs/09-SDLC §4 — per card, not per D1-D14)."""
    gates = list(CORE_GATES)
    joined = "\n".join(changed)
    if any(t in joined for t in UX_TRIGGER):
        gates.append("ux-reviewer")
    if any(t in joined for t in ARCHITECT_TRIGGER):
        gates.append("architect")
    if any(t in joined for t in OPS_TRIGGER):
        gates.append("ops-engineer")
    return gates


# Generated fixture files are named in the prompt but never inlined: their bytes are
# machine-written low-signal bulk (5,400-char repeated-prefix lines) that burns the
# agents' diff budget, and inlining the T-F4 pair was what first pushed the prompt past
# the kernel's 128 KiB per-argv-element cap (MAX_ARG_STRLEN) — every agent died with
# E2BIG/OSError before invocation. Agents that need them read the checkout (TE-3).
GENERATED_DIFF_EXCLUDES = (
    ":!tests/fixtures/*.jsonl",
    ":!tests/fixtures/*.csv",
    ":!tests/fixtures/*.jsonl.gz",
)


def _diff(base: str) -> str:
    out = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--", ".", *GENERATED_DIFF_EXCLUDES],
        capture_output=True,
        text=True,
        check=False,
    )
    # SAME globs as the content exclusion (derived, single source) — querying the
    # whole fixtures dir listed real .py sources (gen_fixtures.py) as "not inlined"
    # while the content diff above showed them in full (G-T-F4 round-4 c.1).
    excluded_globs = [spec[2:] for spec in GENERATED_DIFF_EXCLUDES]
    excluded = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD", "--", *excluded_globs],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if excluded:
        return (
            out.stdout
            + "\n----- generated fixture files changed but NOT inlined "
            + "(read them in the checkout if the review needs their content) -----\n"
            + excluded
            + "\n"
        )
    return out.stdout


def _charter(agent: str) -> str:
    path = AGENTS_DIR / f"{agent}.md"
    return path.read_text(encoding="utf-8") if path.exists() else f"(no charter for {agent})"


def agent_model(agent: str) -> str:
    """TE-5 COST TIERING: a gate agent runs on the model named in its charter
    frontmatter (all `sonnet`), NOT the caller's default tier. Read only the YAML
    frontmatter block, and default to `sonnet` so a missing/renamed field can never
    silently escalate a gate to the Opus tier (which is what breaks the cost profile)."""
    parts = _charter(agent).split("---", 2)
    front = parts[1] if len(parts) >= 3 else ""
    m = re.search(r"^model:\s*(\S+)", front, re.MULTILINE)
    return m.group(1) if m else "sonnet"


# The gate agents are read-plus-run reviewers: they must be able to execute the pinned
# toolchain (`uv run pytest`/`ruff`, TE-11) and read the tree, or they fall back to
# static review and cannot verify green (vv/system-tester/ops finding). Headless `-p`
# denies any tool not listed, so name exactly the reviewer set — no writes, no network.
_ALLOWED_TOOLS = "Read,Grep,Glob,Bash"


def _looks_truncated(out: str) -> bool:
    """True when an agent's output is ONLY a verdict token (or empty) — no findings.

    A real gate review always carries reasoning/findings beyond the single TE-8 verdict
    line; the charter requires numbered file:line findings for any non-clean verdict. A
    bare `VERDICT: FAIL` with nothing else is a truncated/errored model response, seen
    intermittently from cold-reviewer (PRs #69, #75) — NOT a valid verdict, and it must
    not be able to block a merge on emptiness. Worth exactly one retry. The deterministic
    `[harness] … NO-VERDICT.` strings carry no verdict token and are long enough to read
    as substantive here, so they are never retried (a timeout/crash retry is pointless)."""
    body = (out or "").strip()
    if not body:
        return True
    without_verdict = _VERDICT_RE.sub("", body).strip()
    if len(without_verdict) >= 20:
        return False
    # Only a verdict token survived. Truncation removes the TAIL, and the verdict line
    # IS the tail — so a verdict token being PRESENT is evidence the reply completed.
    # A bare `VERDICT: PASS` is therefore a legitimate terse clean pass: the charter
    # demands numbered file:line findings only for NON-clean verdicts, so a reviewer
    # with nothing to report owes no findings. Treating it as truncation retried a valid
    # review and, when the reviewer was tersely clean twice, converted a PASS into a
    # merge-blocking NO-VERDICT (observed on PR #111: the round blocked, the rerun
    # returned the same PASS, and nothing in the diff had changed).
    # Bare FAIL / PASS-WITH-NOTES stay truncated — those verdicts are charter-invalid
    # without findings, and are the responses actually seen on PRs #69 and #75.
    return parse_verdict(body) != "PASS"


def _invoke_cli(agent: str, prompt: str) -> str:
    """One headless `claude -p` call as this gate agent. A crash/timeout/missing-CLI maps
    to NO-VERDICT (which blocks) rather than tearing down the whole round with a bare
    traceback and no comment (cold-reviewer finding). `--model` is forced from the charter
    so the round stays on Sonnet (TE-5) regardless of the runner's default tier."""
    try:
        # The prompt travels on STDIN, never as an argv element: a prompt carrying a
        # large diff blows the kernel's per-argument cap (MAX_ARG_STRLEN, 128 KiB) and
        # execve fails with E2BIG before the CLI even starts — which is how the whole
        # T-F4 round died five-for-five, twice. stdin has no such cap.
        proc = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                agent_model(agent),
                "--allowedTools",
                _ALLOWED_TOOLS,
                "--output-format",
                "text",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=AGENT_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"[harness] {agent} exceeded the {AGENT_TIMEOUT_S}s budget — recorded as NO-VERDICT."
    except Exception as exc:
        # Broad ON PURPOSE: a missing CLI (FileNotFoundError), a denied exec
        # (PermissionError), a decode error from text=True (UnicodeDecodeError) — ANY
        # failure of ONE gate must degrade to NO-VERDICT for that gate, never crash the
        # whole round and take the other gates' results down with it.
        return f"[harness] {agent} invocation failed ({type(exc).__name__}) — NO-VERDICT."
    # No VERDICT token in an error tail => parse_verdict returns NO-VERDICT (blocks).
    return proc.stdout + ("\n" + proc.stderr if proc.returncode != 0 else "")


def _run_agent_live(agent: str, diff_text: str, base: str) -> str:
    """Invoke this gate agent over the PR diff, retrying up to `ATTEMPTS_ON_TRUNCATION`
    times if the response is a truncated verdict-only reply (see `_looks_truncated`), and
    surfacing the raw replies if every attempt fails so the block is diagnosable."""
    truncated = len(diff_text) > DIFF_CAP
    marker = f" (TRUNCATED — first {DIFF_CAP} chars only; coverage is partial)" if truncated else ""
    prompt = (
        f"You are the {agent} gate. Follow this charter exactly:\n\n{_charter(agent)}\n\n"
        f"Review ONLY the changes in this PR: `git diff {base}...HEAD` (shown below). "
        "Obey TE-2 (diff + STATUS + your charter docs only), TE-6 (<=15 tool calls), "
        "TE-11 (pinned `uv run` toolchain). "
        "The FULL test suite, lint and type-check ALREADY run as REQUIRED CI checks that "
        "gate this merge independently — do NOT re-run the whole suite here (it will "
        "exhaust your time budget and record a NO-VERDICT). Validate the DIFF: if a test "
        "run helps, execute ONLY the changed/added test files (`uv run pytest <those "
        "files> -q`) and reason about the rest. End your reply with EXACTLY one line:\n"
        "VERDICT: <PASS | PASS-WITH-NOTES | FAIL>\n\n"
        f"----- diff{marker} -----\n{diff_text[:DIFF_CAP]}\n"
    )
    # A verdict-only reply is not a review. Retry in-process rather than asking a human
    # to press the button the harness already knows to press: on 2026-08-01 cold-reviewer
    # NO-VERDICTed the same code diff across five separate rounds while three other gates
    # reviewed it substantively every time, and every occurrence cost a manual re-run.
    attempts: list[str] = []
    for _ in range(ATTEMPTS_ON_TRUNCATION):
        out = _invoke_cli(agent, prompt)
        if not _looks_truncated(out):
            return out
        attempts.append(out)
    # Still nothing after every attempt. Surface WHAT came back, bounded — a NO-VERDICT
    # that cannot say why is undiagnosable, which is how this went five rounds unexplained.
    # Neutralise verdict tokens INSIDE the excerpt before quoting it: parse_verdict takes
    # the LAST match in the text, so an un-redacted excerpt makes the diagnostic message
    # itself parse as a verdict — this NO-VERDICT would have read as FAIL (caught by
    # test_persistent_truncation_becomes_no_verdict_not_a_bare_fail the moment it was added).
    seen = " | ".join(
        repr(_VERDICT_RE.sub("<verdict-token>", a.strip()[:120])) if a.strip() else "<empty>"
        for a in attempts
    )
    return (
        f"[harness] {agent} returned a verdict with no findings on all "
        f"{ATTEMPTS_ON_TRUNCATION} automatic attempts — recorded as NO-VERDICT. "
        f"Automatic retries are EXHAUSTED, so a plain re-run is unlikely to help; "
        f"investigate the agent or the diff. Raw replies: {seen}"
    )


def run_round(base: str, dry_run: bool, mock: dict[str, str] | None = None) -> list[GateResult]:
    changed = _changed_files(base)
    gates = select_gates(changed)
    diff_text = "" if dry_run else _diff(base)
    results: list[GateResult] = []
    for agent in gates:
        if dry_run:
            out = (mock or {}).get(agent, "VERDICT: PASS")
        else:
            out = _run_agent_live(agent, diff_text, base)
        results.append(GateResult(agent=agent, verdict=parse_verdict(out), output=out))
    return results


_MARK = {"PASS": "✅", "PASS-WITH-NOTES": "⚠️", "FAIL": "❌", "NO-VERDICT": "❓"}
_FINDINGS_CAP = 6000  # keep each agent's block well under GitHub's 65 536-char comment cap


def to_comment(results: list[GateResult]) -> str:
    lines = ["## Gate round (LE-4)", "", "| Gate | Verdict |", "|------|---------|"]
    for r in results:
        lines.append(f"| {r.agent} | {_MARK.get(r.verdict, '❓')} {r.verdict} |")
    blocked = [r.agent for r in results if r.verdict in ("FAIL", "NO-VERDICT")]
    lines += ["", ("**BLOCKED** — " + ", ".join(blocked)) if blocked else "**All gates cleared.**"]
    # A gate's NOTES are the whole point of a gate — surface every non-clean verdict's
    # findings inline (collapsed) so PASS-WITH-NOTES is ACTIONABLE on the PR, not lost in
    # the run log. A clean PASS carries nothing to resolve, so it stays a table row only.
    for r in results:
        if r.verdict == "PASS":
            continue
        body = (r.output or "").strip()
        if len(body) > _FINDINGS_CAP:
            body = "…(truncated; full text in the CI log)…\n" + body[-_FINDINGS_CAP:]
        lines += [
            "",
            f"<details><summary>{_MARK.get(r.verdict, '❓')} {r.agent} — {r.verdict}</summary>",
            "",
            "```",
            body or "(no output captured)",
            "```",
            "</details>",
        ]
    return "\n".join(lines)


def is_blocking(results: list[GateResult]) -> bool:
    # FAIL or NO-VERDICT blocks; PASS-WITH-NOTES does not block the CHECK (its notes are
    # resolved before Done per docs/09-SDLC §3, tracked on the PR, not by this gate).
    return any(r.verdict in ("FAIL", "NO-VERDICT") for r in results)


def main() -> int:
    ap = argparse.ArgumentParser(description="LE-4 gate round in CI")
    ap.add_argument("--base", default="origin/main", help="diff base ref")
    ap.add_argument("--dry-run", action="store_true", help="mock agents (no API); test the harness")
    ap.add_argument("--comment-out", help="write the PR-comment markdown to this path")
    args = ap.parse_args()

    results = run_round(args.base, dry_run=args.dry_run)
    # Full per-agent output to the CI log first (untruncated backup), then the comment.
    for r in results:
        if not args.dry_run:
            print(f"\n===== {r.agent} ({r.verdict}) =====\n{(r.output or '').strip()}")
    comment = to_comment(results)
    print(comment)
    if args.comment_out:
        Path(args.comment_out).write_text(comment, encoding="utf-8")
    return 1 if is_blocking(results) else 0


if __name__ == "__main__":
    sys.exit(main())
