"""R-LIVE-PRICING — autonomous pricing sync (no human gate).

Ops tooling, NOT engine code: this module MAY import network (urllib); it lives
under scripts/ so services/pricing stays network-free (NFR-01 / T-NFR-01). It
fetches a STRUCTURED pricing feed (LiteLLM's model_prices_and_context_window
JSON — the same source R-PRICING-AGENT already trusted as its cross-check),
runs automated validation GATES that stand in for the removed human approver,
and writes gate-passing, effective-dated rows into the machine-managed overlay
prices.auto.yaml. The hand-commented base prices.yaml is never touched.

Two modes:
  * default (daily ofelia)  — REFRESH: re-price models already in the table so
    they never go stale; large swings are held for safety, not applied blind.
  * --cover a,b,c           — COVER leftover jobs: price models seen in usage
    but absent from the table (the gpt-4o-mini incident), back-dated to span
    the audit window so the triggering usage actually prices.

A blank/absent feed price is NEVER written as $0 (R-LIVE-PRICING gate). A model
no source publishes stays unpriced and surfaces honestly via the clarity state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml

from tokenops_cost_auditor.services.pricing.table import AUTO_DATA, DEFAULT_DATA, PricingTable

LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
PROVIDERS = {"openai", "anthropic"}  # the providers we price
MAX_RATE = 1000.0  # $/1M ceiling — a plausible upper band (gate 2)
JUMP = 0.60  # a >±60% change to an EXISTING rate is held, not auto-applied (gate 4)
COVERAGE_BACKDATE_DAYS = 90  # new-model coverage spans typical audit windows
FETCH_TIMEOUT_S = 30
REPORT_DIR = Path("/data/reports")  # prod REPORT_DIR; overridable via --report-dir
# a trailing dated snapshot, e.g. -2024-07-18 or -20240718 (mirrors table.rate's
# "-2..." suffix rule) — stripped so "gpt-4o-mini-2024-07-18" covers via bare id.
DATED_SUFFIX_RE = re.compile(r"-2\d{3}(?:-?\d{2}){0,2}$")


def fetch_litellm(url: str = LITELLM_URL) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "tokenops-pricing-sync/1.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_per_million(cost_per_token: object) -> float | None:
    try:
        return round(float(cost_per_token) * 1_000_000, 6)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def base_id(model: str) -> str:
    """Strip a trailing dated snapshot so a bare id covers its dated siblings."""
    return DATED_SUFFIX_RE.sub("", model)


def normalize(data: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Feed JSON -> {(provider, model_id): four per-1M rates}. Keeps only the
    providers we price; drops rows without a usable input+output pair."""
    out: dict[tuple[str, str], dict[str, float]] = {}
    for raw_id, spec in data.items():
        if raw_id == "sample_spec" or not isinstance(spec, dict):
            continue
        provider = str(spec.get("litellm_provider", "")).lower()
        if provider not in PROVIDERS:
            continue
        inp = to_per_million(spec.get("input_cost_per_token"))
        outp = to_per_million(spec.get("output_cost_per_token"))
        if inp is None or outp is None or inp <= 0 or outp <= 0:
            continue  # free/unpriced/malformed — never written as $0
        cache_read = to_per_million(spec.get("cache_read_input_token_cost"))
        cache_write = to_per_million(spec.get("cache_creation_input_token_cost"))
        # LiteLLM keys can carry a "provider/" prefix; our ids are bare.
        model_id = raw_id.split("/", 1)[1] if "/" in raw_id else raw_id
        out[(provider, model_id.lower())] = {
            "input": inp,
            "output": outp,
            # sane fallbacks (Rate defaults these to input when absent/implausible)
            "cache_read": cache_read if cache_read is not None and 0 <= cache_read <= inp else inp,
            "cache_write": cache_write if cache_write is not None and cache_write >= 0 else inp,
        }
    return out


def gate_band(cand: dict[str, float]) -> str | None:
    """Gate 1+2 — shape + plausible band. Returns a reason string on FAIL."""
    for field in ("input", "output", "cache_read", "cache_write"):
        v = cand.get(field)
        if v is None:
            return f"missing {field}"
        if v < 0 or v > MAX_RATE:
            return f"{field}={v} outside (0, {MAX_RATE}]"
    if cand["input"] <= 0 or cand["output"] <= 0:
        return "input/output must be > 0"
    return None


def _current_rate(table: PricingTable, provider: str, model: str, on: date) -> object | None:
    from tokenops_cost_auditor.services.pricing.table import PricingGapError

    try:
        return table.rate(provider, model, on)
    except PricingGapError:
        return None


def plan(
    table: PricingTable,
    normalized: dict[tuple[str, str], dict[str, float]],
    run_date: date,
    cover: set[str] | None = None,
) -> dict[str, list[dict]]:
    """Decide what to write. REFRESH mode (cover=None) touches only models
    already in the table; COVER mode adds the named unpriced models."""
    writes: list[dict] = []
    held: list[dict] = []
    skipped = 0
    cover_bases = {base_id(m.lower()) for m in cover} if cover else set()

    for (provider, model), cand in sorted(normalized.items()):
        current = _current_rate(table, provider, model, run_date)
        is_cover = model in cover_bases or base_id(model) in cover_bases
        if current is None and not is_cover:
            continue  # REFRESH never bulk-imports the feed's whole universe
        reason = gate_band(cand)
        if reason is not None:
            held.append({"provider": provider, "model": model, "why": f"band: {reason}"})
            continue
        if current is not None:
            # Gate 5 — no-op guard: identical effective rate, nothing to write.
            if (
                abs(current.input - cand["input"]) < 1e-6
                and abs(current.output - cand["output"]) < 1e-6
            ):
                skipped += 1
                continue
            # Gate 4 — jump guard: a large swing on an existing rate is HELD, not
            # applied blind (a one-off feed glitch must not rewrite money math).
            worst = max(
                abs(cand["input"] - current.input) / current.input if current.input else 1,
                abs(cand["output"] - current.output) / current.output if current.output else 1,
            )
            if worst > JUMP:
                held.append(
                    {
                        "provider": provider,
                        "model": model,
                        "why": f"jump {worst:.0%} > {JUMP:.0%} "
                        f"(feed ${cand['input']}/{cand['output']} vs "
                        f"table ${current.input}/{current.output})",
                    }
                )
                continue
            eff = run_date  # a real price change applies going forward
        else:
            # New coverage: back-date so the usage that triggered it actually prices.
            eff = run_date - timedelta(days=COVERAGE_BACKDATE_DAYS)
        writes.append(
            {
                "provider": provider,
                "model": model,
                "effective_from": eff.isoformat(),
                "input": cand["input"],
                "output": cand["output"],
                "cache_write": cand["cache_write"],
                "cache_read": cand["cache_read"],
                "source": "litellm-auto",
            }
        )
    return {"writes": writes, "held": held, "skipped": skipped}


def merge_overlay(existing: dict | None, writes: list[dict], run_date: date) -> dict:
    """Fold new rows into the overlay doc, append-only (never mutate a prior row)."""
    doc = existing or {"version": "", "providers": {}}
    doc["version"] = f"auto-{run_date.isoformat()}"
    doc["last_verified"] = run_date
    providers = doc.setdefault("providers", {})
    for w in writes:
        models = providers.setdefault(w["provider"], {}).setdefault("models", {})
        rows = models.setdefault(w["model"], [])
        row = {
            "effective_from": date.fromisoformat(w["effective_from"]),
            "input": w["input"],
            "output": w["output"],
            "cache_write": w["cache_write"],
            "cache_read": w["cache_read"],
            "source": w["source"],
        }
        # Idempotency: replace a same-date auto row rather than stacking duplicates.
        rows[:] = [r for r in rows if r.get("effective_from") != row["effective_from"]]
        rows.append(row)
        rows.sort(key=lambda r: r["effective_from"])
    return doc


OVERLAY_BANNER = (
    "# MACHINE-MANAGED — do not hand-edit. Written by scripts/pricing_sync.py\n"
    "# (R-LIVE-PRICING): auto-fetched, gate-validated, effective-dated rates,\n"
    "# merged append-only over the hand-verified base prices.yaml at load time.\n"
    "# Delete this file to revert to base-only pricing.\n"
)


def write_overlay(doc: dict, path: Path = AUTO_DATA) -> None:
    path.write_text(OVERLAY_BANNER + yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def write_status(report_dir: Path, payload: dict) -> None:
    status = report_dir / ".ops" / "pricing_sync.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps(payload), encoding="utf-8")


def run(
    run_date: date,
    cover: set[str] | None,
    dry_run: bool,
    url: str,
    report_dir: Path,
) -> dict:
    data = fetch_litellm(url)
    normalized = normalize(data)
    # Reference the module globals explicitly (not load()'s bound defaults) so a
    # test can retarget DEFAULT_DATA/AUTO_DATA by monkeypatching this module.
    table = PricingTable.load(path=DEFAULT_DATA, overlay=AUTO_DATA)
    result = plan(table, normalized, run_date, cover)
    if result["writes"] and not dry_run:
        existing = None
        if AUTO_DATA.exists():
            existing = yaml.safe_load(AUTO_DATA.read_text()) or None
        write_overlay(merge_overlay(existing, result["writes"], run_date), path=AUTO_DATA)
    payload = {
        "ok": True,
        "ran_at": datetime.now(UTC).isoformat(),
        "mode": "cover" if cover else "refresh",
        "written": len(result["writes"]),
        "held": result["held"],
        "skipped": result["skipped"],
        "dry_run": dry_run,
    }
    if report_dir.parent.exists():
        write_status(report_dir, payload)
    return payload


def cover_from_usage(session, settings, url: str, run_date: date, report_dir: Path) -> dict:
    """Self-healing coverage: scan recent usage for models the table can't price,
    cover them from the feed, and re-run the affected source audits so the
    leftover jobs land priced (R-LIVE-PRICING §4). DB-touching orchestration —
    imports are local so the pure money-math core above stays network/DB-free."""
    from sqlalchemy import select

    from tokenops_cost_auditor.persistence.models import Source, SourceUsage
    from tokenops_cost_auditor.services.connectors.source_audit import run_source_audit
    from tokenops_cost_auditor.services.pricing.table import PricingGapError

    since = run_date - timedelta(days=getattr(settings, "connect_backfill_days", 30))
    rows = session.execute(
        select(Source.provider, SourceUsage.model, SourceUsage.source_id)
        .join(Source, Source.id == SourceUsage.source_id)
        .where(SourceUsage.day >= since)
        .distinct()
    ).all()
    table = PricingTable.load(path=DEFAULT_DATA, overlay=AUTO_DATA)
    gaps: set[str] = set()
    affected: set[str] = set()
    for provider, model, source_id in rows:
        try:
            table.rate(provider, model, run_date)
        except PricingGapError:
            gaps.add(model)
            affected.add(source_id)

    if not gaps:
        payload = {
            "ok": True,
            "ran_at": datetime.now(UTC).isoformat(),
            "mode": "cover-from-usage",
            "gaps": 0,
            "written": 0,
        }
        if report_dir.parent.exists():
            write_status(report_dir, payload)
        return payload

    payload = run(run_date, cover=gaps, dry_run=False, url=url, report_dir=report_dir)
    payload["mode"] = "cover-from-usage"
    payload["gaps"] = sorted(gaps)
    # Re-audit affected sources against the freshly-priced table so the empty
    # audit that triggered this is replaced by a correct one.
    if payload.get("written"):
        fresh = PricingTable.load(path=DEFAULT_DATA, overlay=AUTO_DATA)
        reaudited = 0
        for source_id in sorted(affected):
            source = session.get(Source, source_id)
            if source is None:
                continue
            try:
                run_source_audit(session, settings, fresh, source)
                session.commit()
                reaudited += 1
            except Exception:
                session.rollback()
        payload["reaudited"] = reaudited
    if report_dir.parent.exists():
        write_status(report_dir, payload)
    return payload


def _run_from_usage(url: str, run_date: date, report_dir: Path) -> dict:
    """Bootstrap a live session (app-container ofelia job) and cover from usage."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from tokenops_cost_auditor.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        return cover_from_usage(session, settings, url, run_date, report_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous pricing sync (R-LIVE-PRICING).")
    parser.add_argument("--cover", default="", help="comma-separated model ids to price on demand")
    parser.add_argument(
        "--cover-from-usage",
        action="store_true",
        help="scan recent usage for unpriced models, cover them, re-audit affected sources",
    )
    parser.add_argument("--dry-run", action="store_true", help="plan only; write nothing")
    parser.add_argument("--url", default=LITELLM_URL)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--date", default="", help="override run date (ISO); testing only")
    args = parser.parse_args(argv)

    run_date = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    cover = {m.strip() for m in args.cover.split(",") if m.strip()} or None
    try:
        if args.cover_from_usage:
            payload = _run_from_usage(args.url, run_date, Path(args.report_dir))
        else:
            payload = run(run_date, cover, args.dry_run, args.url, Path(args.report_dir))
    except Exception as exc:
        report_dir = Path(args.report_dir)
        if report_dir.parent.exists():
            write_status(
                report_dir,
                {"ok": False, "ran_at": datetime.now(UTC).isoformat(), "error": str(exc)[:200]},
            )
        print(f"pricing-sync FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
