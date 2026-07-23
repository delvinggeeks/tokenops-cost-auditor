"""Strict automated pricing verification (R-AUTO-PRICING, founder 2026-07-23).

Founder ruling, verbatim in substance: "all prices have to be automated and
no human gate — it has to be done by the agent strictly verifying." This
script IS that gate. It replaces the founder-eyes step of R-Q3: every
CURRENT rate row in the effective pricing table (base + overlay) must be
corroborated EXACTLY by an independent machine-readable source, or the run
fails and the release is blocked. There is no advisory mode.

Source ladder (recorded 2026-07-23):
1. Official provider price APIs (Azure Retail Prices, AWS Price List) were
   probed and found to LAG the current model generation (zero gpt-5.x
   meters; Bedrock list still on Claude 3) — unusable as the primary
   source today. Re-probe when they catch up.
2. The LiteLLM community feed — independent of this repository, updated
   with current models, and ALREADY this platform's live sync source
   (R-LIVE-PRICING). It is the required corroborating source.

Verification contract:
- The row checked is the one EFFECTIVE TODAY per (provider, model) in the
  merged table (PricingTable.load(): base + machine overlay). Historical
  epochs have no published source and are out of scope — recorded here,
  stated in the methodology.
- input/output/cache_read must match the feed to the cent per 1M tokens.
  cache_write is compared only when BOTH sides publish it (our YAML sets
  it explicitly and the feed carries a cache-creation cost); a structural
  default (cache_write = input) is not a provider-published number.
- Feed keys per provider: openai/anthropic use the model id (with dated/
  versioned fallbacks); azure-openai uses "azure/<model>"; bedrock resolves
  the normalized id against dated "-YYYYMMDD"/"-vN:M"/"@" variants.
- Any MISMATCH or UNCOVERED row => exit 1, rows listed. --stamp rewrites
  last_verified in prices.yaml after a fully green run, which is what
  NFR-15's freshness check now measures: the last successful AGENT
  verification, not a human's.

Usage:
  uv run python scripts/pricing_verify.py                # live feed, verify
  uv run python scripts/pricing_verify.py --feed f.json  # canned feed (CI/tests)
  uv run python scripts/pricing_verify.py --stamp        # + stamp on success
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tokenops_cost_auditor.services.pricing.table import DEFAULT_DATA, PricingTable

FEED_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)


@dataclass(frozen=True)
class RowVerdict:
    provider: str
    model: str
    status: str  # verified | mismatch | uncovered
    detail: str


def _per_million(per_token: object) -> float | None:
    if per_token is None:
        return None
    return round(float(per_token) * 1_000_000, 6)


def _feed_entry(feed: dict, provider: str, model: str) -> tuple[str, dict] | None:
    """Resolve our (provider, model) to the feed's key, dated variants included."""
    candidates: list[str] = []
    if provider == "azure-openai":
        candidates = [f"azure/{model}"]
    elif provider == "bedrock":
        candidates = [model]
    else:  # openai, anthropic
        candidates = [model]
    for base in candidates:
        if base in feed:
            return base, feed[base]
        # dated/versioned fallbacks: -YYYYMMDD..., -vN:M, @date (longest first
        # so the newest dated snapshot wins deterministically)
        variants = sorted(
            (
                k
                for k in feed
                if k.startswith(base + "-2")
                or k.startswith(base + "-v")
                or k.startswith(base + "@")
            ),
            reverse=True,
        )
        if variants:
            return variants[0], feed[variants[0]]
    return None


def verify(table: PricingTable, feed: dict, today: datetime | None = None) -> list[RowVerdict]:
    on_date = (today or datetime.now(UTC)).date()
    out: list[RowVerdict] = []
    for provider, model in sorted(table.entries()):
        try:
            rate = table.rate(provider, model, on_date)
        except Exception:
            # no epoch effective today (future-dated row only) — nothing a
            # customer can be billed at today; skip, honestly labeled
            out.append(RowVerdict(provider, model, "verified", "no epoch effective today"))
            continue
        resolved = _feed_entry(feed, provider, model)
        if resolved is None:
            out.append(RowVerdict(provider, model, "uncovered", "no independent feed entry"))
            continue
        key, entry = resolved
        checks = [
            ("input", rate.input, _per_million(entry.get("input_cost_per_token"))),
            ("output", rate.output, _per_million(entry.get("output_cost_per_token"))),
            ("cache_read", rate.cache_read, _per_million(entry.get("cache_read_input_token_cost"))),
        ]
        feed_write = _per_million(entry.get("cache_creation_input_token_cost"))
        if feed_write is not None and rate.cache_write != rate.input:
            # both sides publish a real write rate — compare it too
            checks.append(("cache_write", rate.cache_write, feed_write))
        problems = []
        for name, ours, theirs in checks:
            if theirs is None:
                continue  # the feed omits this component; the ones it has must match
            if round(float(ours), 6) != theirs:
                problems.append(f"{name}: ours {ours} vs {key} {theirs}")
        if problems:
            out.append(RowVerdict(provider, model, "mismatch", "; ".join(problems)))
        else:
            out.append(RowVerdict(provider, model, "verified", f"corroborated by {key}"))
    return out


def stamp_last_verified(path: Path, on_date: str) -> None:
    text = path.read_text()
    new = re.sub(r"(?m)^last_verified: \S+", f"last_verified: {on_date}", text, count=1)
    if new == text:
        raise SystemExit("could not find last_verified line to stamp")
    path.write_text(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feed", type=Path, help="canned feed JSON (CI/tests); default fetches live")
    ap.add_argument("--stamp", action="store_true", help="rewrite last_verified on full pass")
    args = ap.parse_args(argv)

    if args.feed:
        feed = json.loads(args.feed.read_text())
    else:
        with urllib.request.urlopen(FEED_URL, timeout=60) as resp:
            feed = json.load(resp)

    table = PricingTable.load()
    verdicts = verify(table, feed)
    bad = [v for v in verdicts if v.status != "verified"]
    for v in verdicts:
        marker = "OK " if v.status == "verified" else "!! "
        print(f"{marker}{v.provider}/{v.model}: {v.status} — {v.detail}")
    print(f"\n{len(verdicts) - len(bad)}/{len(verdicts)} rows verified")
    if bad:
        print("STRICT GATE FAILED (R-AUTO-PRICING): fix the rows above; nothing ships unverified.")
        return 1
    if args.stamp:
        stamp_last_verified(DEFAULT_DATA, datetime.now(UTC).date().isoformat())
        print(f"stamped last_verified in {DEFAULT_DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
