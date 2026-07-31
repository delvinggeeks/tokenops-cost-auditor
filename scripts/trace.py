#!/usr/bin/env python
"""LE-9 — traceability console (docs/09-SDLC §6). One command answers "can a human
walk every requirement down to a test, and every test back up to a requirement?"

Ops tooling, NOT engine code and NOT a product surface: it reads repo documents and
the tests tree, imports nothing from `tokenops_cost_auditor`, and is never mounted in
the customer app (same separation as scripts/pricing_sync.py). Zero third-party deps.

The index is DERIVED — docs/04 is a claim, `tests/` is the ground truth, and this tool
reports where they disagree. Until LE-7 lands (a marker binding each test to its
requirement) the up-direction can only be reported as "unclaimed", never resolved: that
gap is shown honestly rather than hidden.

    uv run python scripts/trace.py status      # text summary + the drift classes
    uv run python scripts/trace.py serve       # local console at http://127.0.0.1:8765
    uv run python scripts/trace.py walk FR-07  # one requirement, top to bottom

`build_index()` and the render helpers are pure so they can be unit-tested without a
server or a network (the loop_status.py precedent).
"""

from __future__ import annotations

import argparse
import html
import http.server
import json
import re
import socketserver
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQS_DOC = ROOT / "docs" / "01-REQUIREMENTS.md"
MATRIX_DOC = ROOT / "docs" / "04-TRACEABILITY.md"
TESTS_DIR = ROOT / "tests"

# A requirement id as docs/01 declares it: "FR-38 (S) ..." / "NFR-01 (M) ..."
REQ_RE = re.compile(r"^(?P<id>(?:FR|NFR)-\d+)\s+\((?P<priority>[A-Z])\)")
# A matrix row: | FR-01 | C1,C2 | modules | test ids | doc |
ROW_RE = re.compile(r"^\|\s*(?P<id>(?:FR|NFR)-\d+)\b(?P<rest>.*)$")
# A test id anywhere: T-ING-01, T-RUL-D1-02, T-NFR-01
TID_RE = re.compile(r"T-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+")
# A range: T-ING-01..04  -> expand to 01,02,03,04
RANGE_RE = re.compile(r"(?P<stem>T-[A-Z0-9]+(?:-[A-Z0-9]+)*-)(?P<lo>\d+)\.\.(?P<hi>\d+)")


@dataclass
class Requirement:
    """One requirement and everything the repo claims about it."""

    id: str
    priority: str
    title: str
    in_matrix: bool = False
    hld: str = ""
    modules: list[str] = field(default_factory=list)
    claimed_tests: list[str] = field(default_factory=list)
    resolved_tests: list[str] = field(default_factory=list)
    dead_tests: list[str] = field(default_factory=list)
    # Advisory only — matrix module cells are informal prose, so this is reported
    # but never allowed to drive status (see module_exists).
    missing_modules: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """red = the chain is broken · amber = partially broken · green = walks."""
        if not self.in_matrix:
            return "red"
        if not self.claimed_tests or not self.resolved_tests:
            return "red"
        if self.dead_tests:
            return "amber"
        return "green"


def expand_ranges(text: str) -> str:
    """'T-ING-01..04' -> 'T-ING-01 T-ING-02 T-ING-03 T-ING-04' (width-preserving)."""

    def _expand(m: re.Match[str]) -> str:
        stem, lo, hi = m.group("stem"), m.group("lo"), m.group("hi")
        width = len(lo)
        return " ".join(f"{stem}{n:0{width}d}" for n in range(int(lo), int(hi) + 1))

    return RANGE_RE.sub(_expand, text)


def parse_requirements(doc: str) -> dict[str, Requirement]:
    out: dict[str, Requirement] = {}
    for line in doc.splitlines():
        m = REQ_RE.match(line)
        if not m:
            continue
        rid = m.group("id")
        title = line[m.end() :].strip()
        # Drop a leading "[ruling 2026-07-28]" provenance tag, keep the sentence.
        title = re.sub(r"^\[[^\]]*\]\s*", "", title)
        out[rid] = Requirement(id=rid, priority=m.group("priority"), title=title[:160])
    return out


def parse_matrix(doc: str) -> dict[str, dict[str, object]]:
    """Matrix rows -> {req_id: {hld, modules, tests}}. Ranges are expanded here."""
    rows: dict[str, dict[str, object]] = {}
    for line in doc.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        tests = sorted(set(TID_RE.findall(expand_ranges(cells[3]))))
        modules = [p.strip() for p in cells[2].split(",") if p.strip()]
        rows[m.group("id")] = {"hld": cells[1], "modules": modules, "tests": tests}
    return rows


def collect_test_ids(tests_dir: Path) -> dict[str, list[str]]:
    """Every test id physically present in tests/, mapped to the files carrying it."""
    found: dict[str, list[str]] = {}
    for path in sorted(tests_dir.rglob("*")):
        if path.is_dir() or path.suffix not in {".py", ".md", ".csv", ".jsonl"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for tid in set(TID_RE.findall(text)):
            found.setdefault(tid, []).append(str(path.relative_to(ROOT)))
    return found


def module_exists(module: str) -> bool:
    """Matrix module cells are informal — code paths ('rules/*', 'web/upload'), bare
    labels ('Ops', 'config') and URL routes ('/breakdown'). Only code paths are
    falsifiable, so everything else is reported as present rather than guessed at."""
    parts = module.split()
    if not parts:
        return True
    token = parts[0].strip().rstrip("*/,")
    if not token or token.startswith("/") or "/" not in token:
        return True  # URL route or bare label — not a file claim, not ours to falsify
    # Matrix cells are informal prose ("rules/findings(EvidenceRef)", "docs/15); trigger-gated").
    # Splitting those on commas yields fragments that are not paths. Only a CLEAN
    # path-shaped token is falsifiable; anything else is reported as present, because a
    # tool that raises false defects gets ignored — which is the failure we are fixing.
    if len(parts) > 1 or any(c in token for c in "()`;§'\""):
        return True
    base = token.split("*")[0].strip("/")
    if not base:
        return True
    # The matrix writes module paths relative to whichever package root reads naturally
    # ('cli.py', 'web/upload', 'rules/d1_oversized_model' — the last living under
    # services/). Resolve against all three rather than assuming one.
    pkg = ROOT / "src" / "tokenops_cost_auditor"
    roots = (pkg, pkg / "services", ROOT)
    if any((r / base).exists() for r in roots):
        return True
    parent, _, stem = base.rpartition("/")
    for r in roots:
        d = r / parent if parent else r
        if d.is_dir() and any(p.name.startswith(stem) for p in d.iterdir()):
            return True
    return False


def build_index() -> dict[str, object]:
    """The whole derived picture. Pure given the repo contents."""
    reqs = parse_requirements(REQS_DOC.read_text(encoding="utf-8"))
    matrix = parse_matrix(MATRIX_DOC.read_text(encoding="utf-8"))
    present = collect_test_ids(TESTS_DIR)

    claimed_anywhere: set[str] = set()
    for rid, req in reqs.items():
        row = matrix.get(rid)
        if not row:
            continue
        req.in_matrix = True
        req.hld = str(row["hld"])
        req.modules = list(row["modules"])  # type: ignore[arg-type]
        req.claimed_tests = list(row["tests"])  # type: ignore[arg-type]
        claimed_anywhere.update(req.claimed_tests)
        req.resolved_tests = [t for t in req.claimed_tests if t in present]
        req.dead_tests = [t for t in req.claimed_tests if t not in present]
        req.missing_modules = [m for m in req.modules if not module_exists(m)]

    # Rows in the matrix for a requirement docs/01 no longer declares.
    stray_rows = sorted(set(matrix) - set(reqs))
    # Tests that exist but no matrix row claims — invisible to the audit (up-direction).
    unclaimed = sorted(set(present) - claimed_anywhere)

    return {
        "requirements": reqs,
        "present_tests": present,
        "stray_rows": stray_rows,
        "unclaimed_tests": unclaimed,
        "totals": {
            "requirements": len(reqs),
            "in_matrix": sum(r.in_matrix for r in reqs.values()),
            "untraced": sum(not r.in_matrix for r in reqs.values()),
            "green": sum(r.status == "green" for r in reqs.values()),
            "amber": sum(r.status == "amber" for r in reqs.values()),
            "red": sum(r.status == "red" for r in reqs.values()),
            "test_ids_present": len(present),
            "test_ids_claimed": len(claimed_anywhere),
            "dead_test_ids": len(claimed_anywhere - set(present)),
            "unclaimed_tests": len(unclaimed),
        },
    }


# ---------------------------------------------------------------- text surface


def render_status(index: dict[str, object]) -> str:
    t = index["totals"]  # type: ignore[index]
    reqs: dict[str, Requirement] = index["requirements"]  # type: ignore[assignment]
    lines = [
        "TRACEABILITY — docs/01 -> docs/04 -> tests/",
        "",
        f"  requirements declared      {t['requirements']:>4}",
        f"    walk clean (green)       {t['green']:>4}",
        f"    partially broken (amber) {t['amber']:>4}",
        f"    broken (red)             {t['red']:>4}",
        f"    no matrix row            {t['untraced']:>4}",
        "",
        f"  test ids present in tests/ {t['test_ids_present']:>4}",
        f"    claimed by the matrix    {t['test_ids_claimed']:>4}",
        f"    DEAD (claimed, absent)   {t['dead_test_ids']:>4}",
        f"    UNCLAIMED (invisible)    {t['unclaimed_tests']:>4}",
    ]
    broken = [r for r in reqs.values() if r.status != "green"]
    if broken:
        lines += ["", "  first broken chains:"]
        for r in broken[:8]:
            why = (
                "no matrix row"
                if not r.in_matrix
                else f"{len(r.dead_tests)} dead test id(s): {', '.join(r.dead_tests[:3])}"
                if r.dead_tests
                else "no resolvable test"
            )
            lines.append(f"    {r.status.upper():<5} {r.id:<7} {why}")
    return "\n".join(lines)


def render_walk(index: dict[str, object], rid: str) -> str:
    reqs: dict[str, Requirement] = index["requirements"]  # type: ignore[assignment]
    present: dict[str, list[str]] = index["present_tests"]  # type: ignore[assignment]
    r = reqs.get(rid)
    if r is None:
        return f"{rid}: not declared in docs/01"
    out = [f"{r.id} ({r.priority})  [{r.status.upper()}]", f"  {r.title}", ""]
    if not r.in_matrix:
        out.append("  NO MATRIX ROW — the chain does not start.")
        return "\n".join(out)
    out += [f"  HLD      {r.hld}", f"  modules  {', '.join(r.modules) or '—'}", "  tests"]
    for t in r.claimed_tests:
        files = present.get(t)
        out.append(f"    {'OK  ' if files else 'DEAD'} {t}" + (f"  -> {files[0]}" if files else ""))
    if not r.claimed_tests:
        out.append("    (none claimed)")
    return "\n".join(out)


# ---------------------------------------------------------------- html surface

CSS = """
:root{--bg:#fff;--fg:#111;--mut:#666;--line:#e3e3e3;--g:#0a7;--a:#c80;--r:#c33;--card:#fafafa}
@media(prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e8e8e8;--mut:#9aa;--line:#272b33;--card:#161920}}
*{box-sizing:border-box}body{margin:0;padding:2rem;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:inherit}h1{font-size:1.35rem;margin:0 0 .25rem}
.sub{color:var(--mut);margin-bottom:1.5rem}
.grid{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:1.75rem}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:.7rem 1rem;min-width:9rem}
.stat b{display:block;font-size:1.5rem;line-height:1.2}.stat span{color:var(--mut);font-size:.8rem}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);
padding:.45rem .6rem;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:.8rem}
.dot{display:inline-block;width:.6rem;height:.6rem;border-radius:50%;margin-right:.45rem}
.green{background:var(--g)}.amber{background:var(--a)}.red{background:var(--r)}
code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
.dead{color:var(--r)}.ok{color:var(--g)}.muted{color:var(--mut)}
.wrap{max-width:64rem;margin:0 auto}.back{color:var(--mut);text-decoration:none;font-size:.85rem}
"""


def _page(title: str, body: str) -> bytes:
    return (
        f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>"
        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<style>{CSS}</style><div class=wrap>{body}</div>"
    ).encode()


def render_dashboard(index: dict[str, object]) -> bytes:
    t = index["totals"]  # type: ignore[index]
    reqs: dict[str, Requirement] = index["requirements"]  # type: ignore[assignment]
    stats = "".join(
        f"<div class=stat><b>{v}</b><span>{k}</span></div>"
        for k, v in [
            ("requirements", t["requirements"]),
            ("walk clean", t["green"]),
            ("partial", t["amber"]),
            ("broken", t["red"]),
            ("dead test ids", t["dead_test_ids"]),
            ("unclaimed tests", t["unclaimed_tests"]),
        ]
    )
    rows = ""
    for r in reqs.values():
        dead = f"<span class=dead>{len(r.dead_tests)} dead</span>" if r.dead_tests else ""
        ok = f"<span class=ok>{len(r.resolved_tests)} ok</span>" if r.resolved_tests else ""
        note = " ".join(x for x in (ok, dead) if x) or "<span class=muted>no tests</span>"
        if not r.in_matrix:
            note = "<span class=dead>no matrix row</span>"
        rows += (
            f"<tr><td><span class='dot {r.status}'></span>"
            f"<a href='/req/{r.id}'><code>{r.id}</code></a></td>"
            f"<td>{r.priority}</td><td>{html.escape(r.title[:88])}</td><td>{note}</td></tr>"
        )
    body = (
        "<h1>Traceability console</h1>"
        "<div class=sub>docs/01 &rarr; docs/04 &rarr; tests/ &middot; "
        f"<a href='/unclaimed'>{t['unclaimed_tests']} tests invisible "
        "to the matrix</a></div>"
        f"<div class=grid>{stats}</div>"
        "<table><tr><th>requirement</th><th>pri</th>"
        "<th>title</th><th>tests</th></tr>"
        f"{rows}</table>"
    )
    return _page("Traceability console", body)


def render_req_page(index: dict[str, object], rid: str) -> bytes:
    reqs: dict[str, Requirement] = index["requirements"]  # type: ignore[assignment]
    present: dict[str, list[str]] = index["present_tests"]  # type: ignore[assignment]
    r = reqs.get(rid)
    if r is None:
        return _page(
            rid,
            f"<a class=back href='/'>&larr; back</a><h1>{html.escape(rid)}</h1>"
            "<p>Not declared in docs/01.</p>",
        )
    tests = ""
    for t in r.claimed_tests:
        files = present.get(t)
        tests += (
            f"<tr><td><code>{t}</code></td><td>"
            + (
                f"<span class=ok>resolves</span></td><td><code>{html.escape(files[0])}</code>"
                if files
                else "<span class=dead>DEAD — no collected test</span></td><td class=muted>—"
            )
            + "</td></tr>"
        )
    if not r.claimed_tests:
        tests = "<tr><td colspan=3 class=muted>no test ids claimed by the matrix</td></tr>"
    mods = (
        "".join(
            f"<li><code>{html.escape(m)}</code>"
            + (" <span class=dead>path not found</span>" if m in r.missing_modules else "")
            + "</li>"
            for m in r.modules
        )
        or "<li class=muted>—</li>"
    )
    body = (
        f"<a class=back href='/'>&larr; all requirements</a>"
        f"<h1><span class='dot {r.status}'></span>{r.id} "
        f"<span class=muted>({r.priority})</span></h1>"
        f"<div class=sub>{html.escape(r.title)}</div>"
        + (
            "<p class=dead><b>No matrix row.</b> The chain does not start.</p>"
            if not r.in_matrix
            else f"<p class=muted>HLD component: <code>{html.escape(r.hld) or '—'}</code></p>"
            f"<h3>Modules</h3><ul>{mods}</ul>"
            "<h3>Tests</h3><table><tr><th>test id</th><th>state</th>"
            f"<th>carried in</th></tr>{tests}</table>"
        )
    )
    return _page(rid, body)


def render_unclaimed(index: dict[str, object]) -> bytes:
    present: dict[str, list[str]] = index["present_tests"]  # type: ignore[assignment]
    unclaimed: list[str] = index["unclaimed_tests"]  # type: ignore[assignment]
    rows = "".join(
        f"<tr><td><code>{t}</code></td><td class=muted><code>"
        f"{html.escape(present[t][0])}</code></td></tr>"
        for t in unclaimed
    )
    body = (
        "<a class=back href='/'>&larr; all requirements</a>"
        f"<h1>{len(unclaimed)} tests invisible to the matrix</h1>"
        "<div class=sub>These exist in <code>tests/</code> but no matrix row claims them, so "
        "the up-direction (test &rarr; requirement) cannot be walked. LE-7 closes this by moving "
        "the link into the test.</div>"
        f"<table><tr><th>test id</th><th>carried in</th></tr>{rows}</table>"
    )
    return _page("Unclaimed tests", body)


def serve(port: int) -> None:
    index = build_index()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            idx = build_index()  # rebuild per request: always current, never stale
            if self.path == "/":
                payload = render_dashboard(idx)
            elif self.path == "/unclaimed":
                payload = render_unclaimed(idx)
            elif self.path.startswith("/req/"):
                payload = render_req_page(idx, self.path.removeprefix("/req/"))
            elif self.path == "/index.json":
                totals = idx["totals"]
                payload = json.dumps(totals, indent=2).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json" if self.path.endswith(".json") else "text/html; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_: object) -> None:
            pass  # quiet

    t = index["totals"]  # type: ignore[index]
    print(f"traceability console  http://127.0.0.1:{port}")
    print(
        f"  {t['green']} clean · {t['amber']} partial · {t['red']} broken · "
        f"{t['dead_test_ids']} dead ids · {t['unclaimed_tests']} unclaimed tests"
    )
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LE-9 traceability console")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="text summary of the trace state")
    w = sub.add_parser("walk", help="walk one requirement top to bottom")
    w.add_argument("req", help="e.g. FR-07")
    s = sub.add_parser("serve", help="local HTML console")
    s.add_argument("--port", type=int, default=8765)
    sub.add_parser("json", help="dump the index totals as JSON")
    a = p.parse_args(argv)

    if a.cmd == "serve":
        serve(a.port)
        return 0
    index = build_index()
    if a.cmd == "status":
        print(render_status(index))
    elif a.cmd == "walk":
        print(render_walk(index, a.req.upper()))
    elif a.cmd == "json":
        print(json.dumps(index["totals"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
