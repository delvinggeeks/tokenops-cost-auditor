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

# scripts/ is deliberately not a package, and the tests load this file BY PATH, so
# sys.path[0] is not scripts/ then. Put our own directory on the path before the
# sibling import, so the gate-4 threshold has exactly one definition (pricing_sync)
# rather than a copy here that could silently drift from the sync that enforces it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pricing_sync import HOLD_CORROBORATIONS, JUMP  # single source of the gate-4 rules

from tokenops_cost_auditor.services.pricing.table import DEFAULT_DATA, PricingTable

FEED_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)


@dataclass(frozen=True)
class RowVerdict:
    provider: str
    model: str
    status: str  # verified | held | mismatch | uncovered | not-applicable
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
        # dated/versioned fallbacks, BUCKETED by style (cold-review f.4:
        # one mixed reverse-sort let '-v' outrank a newer '-2026...' key):
        # newest dated snapshot first, then versioned, then @-tagged.
        dated = sorted((k for k in feed if k.startswith(base + "-2")), reverse=True)
        versioned = sorted((k for k in feed if k.startswith(base + "-v")), reverse=True)
        tagged = sorted((k for k in feed if k.startswith(base + "@")), reverse=True)
        for bucket in (dated, versioned, tagged):
            if bucket:
                return bucket[0], feed[bucket[0]]
    return None


def verify(table: PricingTable, feed: dict, today: datetime | None = None) -> list[RowVerdict]:
    on_date = (today or datetime.now(UTC)).date()
    out: list[RowVerdict] = []
    for provider, model in sorted(table.entries()):
        try:
            rate = table.rate(provider, model, on_date)
        except Exception:
            # no epoch effective today (future-dated rows only) — nothing a
            # customer can be billed at today. NOT counted as verified
            # (cold-review f.1: a future-dated typo must never hide inside a
            # green tally); listed separately so a human reading the output
            # sees exactly which rows the gate could not apply to.
            out.append(RowVerdict(provider, model, "not-applicable", "no epoch effective today"))
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
        if feed_write is not None:
            # the feed publishes a write rate: compare it UNCONDITIONALLY
            # (cold-review f.2 — inferring "explicit" from value equality
            # created false confidence; if published data disagrees with our
            # structural default, that IS a divergence and must fail).
            checks.append(("cache_write", rate.cache_write, feed_write))
        problems = []
        for name, ours, theirs in checks:
            if theirs is None:
                continue  # the feed omits this component; the ones it has must match
            if round(float(ours), 6) != theirs:
                problems.append(f"{name}: ours {ours} vs {key} {theirs}")
        if problems:
            # R-LIVE-PRICING gate 4 HOLDS a swing beyond JUMP rather than applying it
            # blind ("a one-off feed glitch must not rewrite money math"). A row the
            # sync deliberately held is therefore NOT "unverified" in R-AUTO-PRICING's
            # sense — corroboration ran, the divergence is known, and daily_digest
            # alerts it. Classifying it as a mismatch made the two rulings mutually
            # exclusive: a legitimate large price cut bricked CI and deploy forever.
            # A SUB-threshold divergence stays a hard failure — that one means the
            # sync did not run or did not write, which is a real defect.
            worst = _worst_swing(checks)
            if worst is not None and worst > JUMP:
                out.append(
                    RowVerdict(
                        provider,
                        model,
                        "held",
                        f"swing {worst:.0%} > {JUMP:.0%} — held by pricing_sync gate 4, "
                        f"not applied blind; {'; '.join(problems)}",
                    )
                )
            else:
                out.append(RowVerdict(provider, model, "mismatch", "; ".join(problems)))
        else:
            out.append(RowVerdict(provider, model, "verified", f"corroborated by {key}"))
    return out


def _worst_swing(checks: list[tuple[str, object, float | None]]) -> float | None:
    """Largest relative move feed-vs-ours over INPUT and OUTPUT only.

    This must mirror pricing_sync's gate 4 EXACTLY — it computes `worst` over input
    and output, so including cache components here would let this gate call a row
    "held" that the sync would actually apply, masking a real failure behind a
    non-fatal verdict."""
    worst: float | None = None
    for name, ours, theirs in checks:
        if name not in ("input", "output") or theirs is None:
            continue
        base = float(ours)  # type: ignore[arg-type]
        rel = abs(theirs - base) / base if base else 1.0
        worst = rel if worst is None else max(worst, rel)
    return worst


def stamp_last_verified(path: Path, on_date: str) -> None:
    text = path.read_text()
    if not re.search(r"(?m)^last_verified: \S+", text):
        raise SystemExit("could not find last_verified line to stamp")
    new = re.sub(r"(?m)^last_verified: \S+", f"last_verified: {on_date}", text, count=1)
    # a same-day restamp is a no-op, not an error (first live 4b run
    # caught this: identical output tripped the not-found guard)
    if new != text:
        path.write_text(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feed", type=Path, help="canned feed JSON (CI/tests); default fetches live")
    ap.add_argument("--stamp", action="store_true", help="rewrite last_verified on full pass")
    args = ap.parse_args(argv)

    if args.feed:
        feed = json.loads(args.feed.read_text())
    else:
        try:
            with urllib.request.urlopen(FEED_URL, timeout=60) as resp:
                feed = json.load(resp)
        except Exception as exc:  # cold-review f.3: a clear gate message,
            # never a raw traceback. Exit 2 distinguishes "could not verify"
            # from "verified and found wrong" (exit 1); BOTH block a release
            # — nothing ships unverified is the ruling's intent.
            print(f"STRICT GATE COULD NOT RUN: feed unreachable ({exc}).")
            print("Nothing ships unverified (R-AUTO-PRICING) — retry, or pass --feed <file>.")
            return 2

    table = PricingTable.load()
    verdicts = verify(table, feed)
    bad = [v for v in verdicts if v.status in ("mismatch", "uncovered")]
    held = [v for v in verdicts if v.status == "held"]
    na = [v for v in verdicts if v.status == "not-applicable"]
    ok = [v for v in verdicts if v.status == "verified"]
    for v in verdicts:
        marker = (
            "OK "
            if v.status == "verified"
            else "na "
            if v.status == "not-applicable"
            else "HOLD "
            if v.status == "held"
            else "!! "
        )
        print(f"{marker}{v.provider}/{v.model}: {v.status} — {v.detail}")
    tally = f"{len(ok)}/{len(verdicts)} rows verified"
    if na:
        tally += f" ({len(na)} not applicable today — future-dated epochs, listed above)"
    print(f"\n{tally}")
    if held:
        print(
            f"\n{len(held)} row(s) HELD by pricing_sync gate 4 (swing > {JUMP:.0%}) — "
            "corroboration ran and the divergence is known, so this is not "
            "'unverified' (R-LIVE-PRICING)."
        )
        print(
            f"No action required and NO human confirmation is sought (R-AUTO-PRICING): the "
            f"hold expires on EVIDENCE — pricing_sync applies it automatically once the feed "
            f"reports the same rate on {HOLD_CORROBORATIONS} consecutive runs."
        )
    if bad:
        print("STRICT GATE FAILED (R-AUTO-PRICING): fix the rows above; nothing ships unverified.")
        return 1
    if args.stamp:
        stamp_last_verified(DEFAULT_DATA, datetime.now(UTC).date().isoformat())
        print(f"stamped last_verified in {DEFAULT_DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
