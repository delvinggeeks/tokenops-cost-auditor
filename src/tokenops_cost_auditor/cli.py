"""CLI ingestion path (FR-04): `tokenops-cost-auditor audit file --out report.pdf`.

Offline concierge pipeline — no server, no database: ingest -> validate -> price
-> reconcile -> detect -> report (PDF + optional JSON). Exit codes: 0 ok,
2 usage error, 3 audit failed (bad input file).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from tokenops_cost_auditor.config import Settings
from tokenops_cost_auditor.services import ingest
from tokenops_cost_auditor.services.ingest.base import IngestError
from tokenops_cost_auditor.services.ingest.validator import enforce, write_error_file
from tokenops_cost_auditor.services.pricing import coster
from tokenops_cost_auditor.services.pricing.table import PricingTable
from tokenops_cost_auditor.services.report.model import ReportModel
from tokenops_cost_auditor.services.report.render_json import render_json
from tokenops_cost_auditor.services.report.render_pdf import render_pdf
from tokenops_cost_auditor.services.rules.base import DetectorContext
from tokenops_cost_auditor.services.rules.findings import observed_days
from tokenops_cost_auditor.services.rules.registry import run_all

CONSENT = (
    "TokenOps will collect TOKEN COUNTS ONLY from your Claude Code\n"
    "transcripts on this machine: models, timestamps, token totals per\n"
    "call. NEVER a prompt, never a completion, never file contents.\n"
    "Ships happen when YOU run (or cron) `ship`. Revoke any time from\n"
    "Sources in the dashboard — revocation is immediate.\n"
)


def _config_path() -> Path:
    import os

    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "tokenops-cost-auditor" / "device.json"  # R-NAMING: full name, everywhere


def _cmd_link(code: str, server: str) -> int:
    """R-CC-LINK 2: ONE HUMAN ACTION IS THE FLOOR. No flag bypasses the
    prompt; a non-interactive shell is refused, by design."""
    import json
    import socket
    import sys as _sys
    import urllib.request

    print(CONSENT)
    if not _sys.stdin.isatty():
        print("linking needs a person at the prompt — run it interactively (this is a feature)")
        return 2
    answer = input("Type 'I agree' to link this machine: ").strip()
    if answer != "I agree":
        print("not linked — nothing was sent, nothing is collected")
        return 2
    body = json.dumps({"code": code, "hostname": socket.gethostname(), "consent": True}).encode()
    req = urllib.request.Request(
        f"{server.rstrip('/')}/api/v1/collector/link",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # honest server words, not a stack trace
        detail = exc.read().decode(errors="replace")[:300]
        print(f"link refused ({exc.code}): {detail}")
        return 1
    import os

    cfg = _config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    # 0600 at CREATION (cold-review f.3): never a world-readable window
    fd = os.open(cfg, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps({"server": server, "token": payload["device_token"]}))
    print(
        f"linked as {socket.gethostname()} — consent recorded. "
        "Ship with: tokenops-cost-auditor ship"
    )
    return 0


def _cmd_ship(source: Path | None, cron: bool) -> int:
    import hashlib
    import json
    import tempfile
    import urllib.request
    import uuid

    if cron:
        print("30 2 * * * tokenops-cost-auditor ship  # daily 02:30, idempotent (FR-26)")
        return 0
    cfg_path = _config_path()
    if not cfg_path.exists():
        print("not linked — run: tokenops-cost-auditor link <code> (code from Sources)")
        return 2
    cfg = json.loads(cfg_path.read_text())
    from tokenops_cost_auditor.services.collector.transcripts import export

    src = source or Path.home() / ".claude" / "projects"
    out = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    try:
        rows = export(src, out)
        if rows == 0:
            print(f"no transcript usage found under {src} — nothing shipped")
            return 0
        payload = out.read_bytes()
        idem = hashlib.sha256(payload).hexdigest()  # same content = same audit (FR-26)
        boundary = uuid.uuid4().hex
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="collector.jsonl"\r\nContent-Type: application/json\r\n\r\n'
            ).encode()
            + payload
            + f"\r\n--{boundary}--\r\n".encode()
        )
        req = urllib.request.Request(
            f"{cfg['server'].rstrip('/')}/api/v1/collector/ship",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Device-Token": cfg["token"],
                "Idempotency-Key": idem,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            print(f"ship refused ({exc.code}): {exc.read().decode(errors='replace')[:300]}")
            return 1
        state = "replayed (already shipped)" if result.get("replayed") else "accepted"
        print(f"{rows} rows shipped, counts only — audit {result['audit_id']} {state}")
        return 0
    finally:
        out.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tokenops-cost-auditor",
        description="Deterministic LLM API spend audit — logs in, dollar-ranked report out.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    link_cmd = sub.add_parser(
        "link", help="link this machine to your TokenOps account (consent-first)"
    )
    link_cmd.add_argument("code", help="one-shot code from Sources → Link a machine")
    link_cmd.add_argument("--server", default="https://tokenops-cost-auditor.com")
    ship_cmd = sub.add_parser("ship", help="export Claude Code transcript counts and ship them")
    ship_cmd.add_argument(
        "--source", type=Path, default=None, help="transcript dir (default ~/.claude/projects)"
    )
    ship_cmd.add_argument("--cron", action="store_true", help="print the crontab line and exit")
    audit_cmd = sub.add_parser("audit", help="audit a log file and render the report")
    audit_cmd.add_argument("file", type=Path, help="OpenAI/Anthropic JSONL or generic CSV")
    audit_cmd.add_argument("--out", type=Path, default=Path("report.pdf"), help="PDF output path")
    audit_cmd.add_argument("--json", type=Path, default=None, help="also write report JSON here")
    args = parser.parse_args(argv)
    if args.command == "link":
        return _cmd_link(args.code, args.server)
    if args.command == "ship":
        return _cmd_ship(args.source, args.cron)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    table = PricingTable.load()
    try:
        frame, vr = ingest.load(
            args.file,
            max_upload_mb=settings.max_upload_mb,
            prefix_hash_chars=settings.prefix_hash_chars,
        )
        error_file = None
        if vr.errors:
            error_file = write_error_file(vr, args.file.with_suffix(".row_errors.csv"))
            print(f"note: {len(vr.errors)} invalid rows -> {error_file}", file=sys.stderr)
        enforce(vr, error_file)
    except IngestError as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 3

    priced, unpriced = coster.apply(table, frame)
    coster.reconcile(priced, coster.total_spend(priced))
    ctx = DetectorContext(settings=settings, table=table, observed_days=observed_days(priced))
    findings = run_all(priced, ctx)
    report = ReportModel.build(
        audit_id=f"cli-{uuid.uuid4().hex[:8]}",
        priced=priced,
        findings=findings,
        unpriced=unpriced,
        table=table,
    )
    render_pdf(report, args.out)
    if args.json:
        render_json(report, args.json)
    print(
        f"report written to {args.out} — {len(findings)} finding(s), "
        f"${report.monthly_savings_usd:.2f}/month estimated savings "
        f"({report.savings_pct:.1f}% of ${report.monthly_spend_usd:.2f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
