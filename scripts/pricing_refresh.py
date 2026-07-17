"""FR-29 (R-PRICING-OPS): read-only pricing drift check — ops tooling, NOT engine
code (NFR-01 untouched; services/pricing stays network-free).

Fetches every `# source_url:` documented in prices.yaml, extracts CANDIDATE rates
heuristically from the page text, and prints a human-readable DIFF: new model ids
on the page, candidate rate mismatches vs the table, unreachable pages. This
script NEVER writes prices.yaml — a human verifies candidates against the page
and edits the table by hand (money-math discipline, CLAUDE.md rule 4; the
WP-P1.5 hard rules forbid any auto-approval path).

Weekly per runbook §8. Outcome (ok/error) is written to
<REPORT_DIR>/.ops/pricing_refresh.json so the daily digest surfaces failures
(FR-29; scripts/daily_digest.py).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import yaml

PRICES_YAML = (
    Path(__file__).parents[1] / "src/tokenops_cost_auditor/services/pricing/data/prices.yaml"
)
FETCH_TIMEOUT_S = 20
# model-id shapes we treat as candidates when seen on a pricing page
MODEL_ID_RE = re.compile(
    r"\b(claude-[a-z0-9][a-z0-9.\-]+|gpt-[0-9][a-z0-9.\-]*|o[0-9][a-z0-9.\-]*)\b"
)
# dollar amounts like $3, $3.00, $12.50 (per-1M-token rates on both providers' pages)
PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
NEARBY_CHARS = 400  # window after a model id in which its rates are expected


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def source_urls(yaml_text: str) -> list[str]:
    """The documented `# source_url:` comment lines (FR-29 'documented source_urls')."""
    return re.findall(r"#\s*source_url:\s*(\S+)", yaml_text)


def table_models(yaml_text: str) -> dict[str, dict[str, float]]:
    """model id -> latest rate row (input/output/...) from prices.yaml, read-only."""
    data = yaml.safe_load(yaml_text)
    models: dict[str, dict[str, float]] = {}
    for provider in data.get("providers", {}).values():
        for model_id, rows in provider.get("models", {}).items():
            latest = max(rows, key=lambda r: str(r.get("effective_from", "")))
            models[model_id] = {k: float(v) for k, v in latest.items() if k != "effective_from"}
    return models


def extract_candidates(page_text: str, known: dict[str, dict[str, float]]) -> dict[str, object]:
    """Heuristic per-page extraction: which known models appear, the first two
    dollar figures near each (candidate input/output), and unknown model ids."""
    found: dict[str, list[float]] = {}
    for model_id in known:
        idx = page_text.find(model_id)
        if idx == -1:
            continue
        window = page_text[idx : idx + NEARBY_CHARS]
        found[model_id] = [float(m) for m in PRICE_RE.findall(window)[:2]]
    new_ids = sorted(
        {
            m
            for m in MODEL_ID_RE.findall(page_text)
            if not any(m.startswith(k) or k.startswith(m) for k in known)
        }
    )
    return {"found": found, "new_ids": new_ids}


def diff_lines(
    url: str, candidates: dict[str, object], known: dict[str, dict[str, float]]
) -> list[str]:
    lines = [f"Source: {url}", "  reachable: yes"]
    found: dict[str, list[float]] = candidates["found"]  # type: ignore[assignment]
    new_ids: list[str] = candidates["new_ids"]  # type: ignore[assignment]
    lines.append(f"  known models seen on page: {len(found)}/{len(known)}")
    if new_ids:
        lines.append(f"  NEW model ids on page (not in prices.yaml): {', '.join(new_ids)}")
    mismatches = []
    for model_id, rates in sorted(found.items()):
        if len(rates) < 2:
            continue
        cand_in, cand_out = rates[0], rates[1]
        table = known[model_id]
        if cand_in != table.get("input") or cand_out != table.get("output"):
            mismatches.append(
                f"    - {model_id}: page ${cand_in}/{cand_out} vs table "
                f"${table.get('input')}/{table.get('output')} — VERIFY BY HAND"
            )
    if mismatches:
        lines.append("  candidate rate mismatches (heuristic):")
        lines.extend(mismatches)
    else:
        lines.append("  no candidate rate mismatches detected")
    return lines


def write_status(report_dir: Path, ok: bool, error: str = "") -> None:
    status_path = report_dir / ".ops" / "pricing_refresh.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"ok": ok, "ran_at": datetime.now(UTC).isoformat(), "error": error}),
        encoding="utf-8",
    )


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "tokenops-pricing-refresh/1.0"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
        return str(response.read().decode("utf-8", errors="replace"))


def main() -> int:
    from tokenops_cost_auditor.config import Settings

    report_dir = Path(Settings().report_dir)
    yaml_text = PRICES_YAML.read_text(encoding="utf-8")
    known = table_models(yaml_text)
    urls = source_urls(yaml_text)
    print(
        f"PRICING REFRESH — read-only diff vs prices.yaml "
        f"({len(known)} models, {len(urls)} sources)"
    )
    print("This tool NEVER writes prices.yaml (FR-29).\n")
    unreachable: list[str] = []
    for url in urls:
        try:
            page = strip_html(fetch(url))
        except Exception as exc:  # every fetch failure is report content here (FR-29)
            unreachable.append(f"{url} ({exc})")
            print(f"Source: {url}\n  reachable: NO ({exc})")
            continue
        for line in diff_lines(url, extract_candidates(page, known), known):
            print(line)
        print()
    if unreachable:
        print(f"UNREACHABLE pages: {len(unreachable)} — retry or check by hand (FR-29)")
        write_status(report_dir, ok=False, error=f"{len(unreachable)} source page(s) unreachable")
        return 1
    write_status(report_dir, ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
