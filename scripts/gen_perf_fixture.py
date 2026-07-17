"""F7 perf fixture generator (docs/05 §2: perf_1m.jsonl.gz, seeded RNG).

Emits N rows (default 1,000,000) of realistic mixed traffic in OpenAI JSONL
shape — priced models only, spanning 30 UTC days, with planted waste so
T-PERF-01 exercises every detector at scale: a cached-prefix route (D2), a
retry-prone route (D4), a chatty agent route (D6), a bloated-prompt route
(D3), a short-completion frontier route (D1), and declared max_tokens (D5).
Deterministic for a given --seed; no text fields anywhere (FR-22).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

# OpenAI-shaped fixture -> provider "openai" on every row: all models must be
# priced OpenAI keys or they land in the unpriced list and skip detection
MODELS = [
    ("gpt-5.5", 0.30),
    ("gpt-5.4-mini", 0.25),
    ("gpt-5.6-terra", 0.20),
    ("gpt-5.4-nano", 0.15),
    ("gpt-5.6-luna", 0.10),
]
START = datetime(2026, 6, 1, tzinfo=UTC)
SPAN_DAYS = 30


def fake_hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def row(rng: random.Random, i: int, n: int) -> dict[str, object]:
    ts = START + timedelta(seconds=rng.uniform(0, SPAN_DAYS * 86400))
    pick = rng.random()
    acc = 0.0
    model = MODELS[-1][0]
    for m, w in MODELS:
        acc += w
        if pick <= acc:
            model = m
            break
    route = rng.random()
    record: dict[str, object] = {
        "created": int(ts.timestamp()),
        "model": model,
        "usage": {
            "prompt_tokens": rng.randint(200, 3000),
            "completion_tokens": rng.randint(50, 900),
        },
        "id": f"req_{i}",
    }
    usage: dict[str, object] = record["usage"]  # type: ignore[assignment]
    if route < 0.10:  # D2: heavy shared-prefix route, uncached
        record["model"] = "gpt-5.6-terra"
        usage["prompt_tokens"] = rng.randint(1800, 2200)
        record["tag"] = "support-bot"
        record["prefix_hash"] = fake_hash("support-system-prompt")
    elif route < 0.13:  # D4: retry bursts — identical fingerprints, tight timing
        burst_anchor = int(route * 1e6) % 500
        record["model"] = "gpt-5.4-mini"
        usage["prompt_tokens"] = 500
        usage["completion_tokens"] = 200
        record["created"] = int(
            (START + timedelta(hours=burst_anchor, seconds=rng.randint(0, 60))).timestamp()
        )
        record["tag"] = "extractor"
        record["prefix_hash"] = fake_hash(f"retry-burst-{burst_anchor}")
    elif route < 0.18:  # D6: chatty agent runs — short completions, shared context
        run_id = int(route * 1e6) % 800
        record["model"] = "gpt-5.4-nano"
        usage["prompt_tokens"] = rng.randint(1000, 1400)
        usage["completion_tokens"] = rng.randint(40, 120)
        record["created"] = int(
            (START + timedelta(hours=run_id % 720, seconds=rng.randint(0, 550))).timestamp()
        )
        record["tag"] = "agent-fleet"
        record["prefix_hash"] = fake_hash(f"agent-context-{run_id}")
    elif route < 0.22:  # D3: bloated prompts on one route
        record["tag"] = "rag-search"
        usage["prompt_tokens"] = rng.randint(5000, 7000)
        usage["completion_tokens"] = rng.randint(256, 500)
    elif route < 0.26:  # D1: mapped-tier model, short mechanical completions
        record["model"] = "gpt-5.5"
        record["tag"] = "tagger"
        usage["prompt_tokens"] = rng.randint(1200, 1800)
        usage["completion_tokens"] = rng.randint(20, 100)
    elif route < 0.30:  # D5: huge declared cap vs tiny outputs
        record["model"] = "gpt-5.6-luna"
        record["tag"] = "notifier"
        record["request"] = {"max_tokens": 8192}  # parser reads request.max_tokens
        usage["completion_tokens"] = rng.randint(60, 140)
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=20260717)
    ap.add_argument("--out", type=Path, default=Path("tests/fixtures/perf_1m.jsonl.gz"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as fh:
        for i in range(args.rows):
            fh.write(json.dumps(row(rng, i, args.rows)) + "\n")
    print(f"wrote {args.rows} rows -> {args.out} ({args.out.stat().st_size / 1e6:.1f} MB gz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
