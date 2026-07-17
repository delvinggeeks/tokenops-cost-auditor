"""Deterministic fixture generator (docs/05 §2). Seeded RNG; committed outputs are
canonical — regenerate ONLY when the fixture spec changes, and commit the diff.

Usage: uv run python tests/fixtures/gen_fixtures.py [outdir]
Generates: F1 openai_small.jsonl (500 clean) · F2 anthropic_small.jsonl (500 clean)
· F3 mixed_dirty.jsonl (500 rows, exactly 8% invalid — FR-03 path) · F4 generic.csv
· claude_code_session.jsonl (FR-24 exporter fixture).
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20260717
BASE_TS = datetime(2026, 6, 1, 8, 0, 0, tzinfo=UTC)

OPENAI_MODELS = ["gpt-5.6-terra", "gpt-5.4-mini", "gpt-5.4-nano"]
ANTHROPIC_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]
TAGS = ["chat-api", "summarizer", "extraction", "support-bot"]


def _openai_line(rng: random.Random, i: int) -> dict[str, object]:
    ts = BASE_TS + timedelta(seconds=i * 37)
    prompt = rng.randint(200, 6000)
    cached = rng.choice([0, 0, 0, rng.randint(0, prompt // 2)])
    return {
        "request_id": f"oai-{i:05d}",
        "ts": ts.isoformat(),
        "endpoint": "/v1/chat/completions",
        "tag": rng.choice(TAGS),
        "latency_ms": round(rng.uniform(180, 4200), 1),
        "team": rng.choice(["growth", "platform"]),  # unknown field -> raw_extra
        "request": {
            "max_tokens": rng.choice([1024, 4096, 8192]),
            "messages": [
                {"role": "system", "content": f"You are assistant profile {i % 7}."},
                {"role": "user", "content": f"Task {i}: summarize item {rng.randint(1, 99)}"},
            ],
        },
        "response": {
            "id": f"chatcmpl-{i:05d}",
            "object": "chat.completion",
            "created": int(ts.timestamp()),
            "model": rng.choice(OPENAI_MODELS),
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": rng.randint(20, 900),
                "total_tokens": 0,
                "prompt_tokens_details": {"cached_tokens": cached},
            },
        },
    }


def _anthropic_line(rng: random.Random, i: int) -> dict[str, object]:
    ts = BASE_TS + timedelta(seconds=i * 41)
    base_input = rng.randint(150, 5000)
    cache_read = rng.choice([0, 0, rng.randint(0, 3000)])
    cache_write = rng.choice([0, 0, 0, rng.randint(0, 1500)])
    return {
        "request_id": f"ant-{i:05d}",
        "ts": ts.isoformat(),
        "endpoint": "/v1/messages",
        "tag": rng.choice(TAGS),
        "latency_ms": round(rng.uniform(200, 5100), 1),
        "env": rng.choice(["prod", "staging"]),  # unknown field -> raw_extra
        "request": {
            "max_tokens": rng.choice([1024, 2048, 8192]),
            "system": f"System profile {i % 5}.",
            "messages": [{"role": "user", "content": f"Request {i}: classify record {i * 3}"}],
        },
        "response": {
            "id": f"msg_{i:05d}",
            "type": "message",
            "role": "assistant",
            "model": rng.choice(ANTHROPIC_MODELS),
            "usage": {
                "input_tokens": base_input,
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": cache_read,
                "output_tokens": rng.randint(15, 1100),
            },
        },
    }


def _dirty_lines(rng: random.Random, n: int, bad: int) -> list[str]:
    """n rows total; exactly `bad` invalid with mixed error kinds (F3 exercises the
    FR-03 row-error path). Single provider: format detection is per-file, so a
    multi-provider JSONL is a format error, not a row-error case."""
    bad_idx = set(rng.sample(range(n), bad))
    lines: list[str] = []
    for i in range(n):
        if i in bad_idx:
            kind = i % 4
            if kind == 0:
                lines.append("{not valid json%%")
            elif kind == 1:
                lines.append(json.dumps(["a", "list", "not", "object"]))
            elif kind == 2:  # missing usage -> missing prompt_tokens
                lines.append(
                    json.dumps(
                        {
                            "response": {
                                "id": f"bad-{i}",
                                "object": "chat.completion",
                                "created": int(BASE_TS.timestamp()),
                                "model": "gpt-5.2",
                            }
                        }
                    )
                )
            else:  # invalid timestamp
                row = _openai_line(rng, i)
                row["ts"] = "not-a-date"
                resp = row["response"]
                assert isinstance(resp, dict)
                resp["created"] = None
                lines.append(json.dumps(row))
        else:
            lines.append(json.dumps(_openai_line(rng, i)))
    return lines


def _csv_lines(rng: random.Random, n: int) -> list[str]:
    header = (
        "ts,provider,model,prompt_tokens,completion_tokens,cached_tokens,"
        "latency_ms,endpoint,request_id,tag,declared_max_tokens,cost_center"
    )
    rows = [header]
    for i in range(n):
        ts = (BASE_TS + timedelta(seconds=i * 53)).isoformat()
        provider = rng.choice(["openai", "anthropic"])
        model = rng.choice(OPENAI_MODELS if provider == "openai" else ANTHROPIC_MODELS)
        rows.append(
            f"{ts},{provider},{model},{rng.randint(100, 4000)},{rng.randint(10, 800)},"
            f"{rng.choice([0, 0, 512])},{round(rng.uniform(150, 3000), 1)},/v1/chat,"
            f"csv-{i:04d},{rng.choice(TAGS)},{rng.choice(['', '4096'])},cc-{i % 3}"
        )
    return rows


def _claude_code_session(rng: random.Random, n_msgs: int) -> list[str]:
    """Synthetic Claude Code transcript: user/assistant/progress lines; only
    assistant lines carry usage. Content strings present (exporter must DROP them)."""
    lines: list[str] = []
    session = "0a1b2c3d-sess-fixture"
    for i in range(n_msgs):
        ts = (BASE_TS + timedelta(seconds=i * 9)).isoformat()
        lines.append(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": session,
                    "timestamp": ts,
                    "message": {"role": "user", "content": f"SECRET-USER-PROMPT-{i}"},
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": session,
                    "timestamp": (BASE_TS + timedelta(seconds=i * 9 + 4)).isoformat(),
                    "message": {
                        "id": f"msg_cc_{i:04d}",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-opus-4-8",
                        "content": [{"type": "text", "text": f"SECRET-ASSISTANT-REPLY-{i}"}],
                        "usage": {
                            "input_tokens": rng.randint(400, 9000),
                            "cache_creation_input_tokens": rng.choice([0, rng.randint(100, 2000)]),
                            "cache_read_input_tokens": rng.choice([0, rng.randint(500, 8000)]),
                            "output_tokens": rng.randint(30, 700),
                        },
                    },
                }
            )
        )
        if i % 5 == 0:
            lines.append(json.dumps({"type": "progress", "sessionId": session, "timestamp": ts}))
    return lines


# --- D4-milestone fixtures: engineered waste + false-positive guard (docs/05 F5/F6) ---

D2_PREFIX_TEXT = "CACHE-ME " * 600  # 5400 chars > PREFIX_HASH_CHARS: hash covers 4096
D4_RETRY_TEXT = "RETRY-ME payload identical request body " * 4


def _waste_pack_lines() -> list[str]:
    """Engineered traffic: EACH detector fires with KNOWN golden savings
    (derivation + expected values in tests/fixtures/pricing_golden_NOTES.md).
    All timestamps span exactly 3 distinct UTC days (2026-06-10..12) so the
    monthly extrapolation factor is exactly 10 (30/3)."""
    lines: list[str] = []
    # D2 block: 30 identical-prefix anthropic sonnet-5 calls, uncached, spaced 130s
    # (gap > 120s keeps D4 silent); prompt 2000 >= 1024; day 1.
    base = datetime(2026, 6, 10, 9, 0, 0, tzinfo=UTC)
    for i in range(30):
        ts = base + timedelta(seconds=130 * i)
        lines.append(
            json.dumps(
                {
                    "request_id": f"wp-d2-{i:03d}",
                    "ts": ts.isoformat(),
                    "endpoint": "/v1/messages",
                    "tag": "summarizer",
                    "request": {
                        "max_tokens": 256,
                        "system": D2_PREFIX_TEXT,
                        "messages": [{"role": "user", "content": "vary-" + str(i)}],
                    },
                    "response": {
                        "id": f"msg_wp_d2_{i:03d}",
                        "type": "message",
                        "model": "claude-sonnet-5",
                        "usage": {
                            "input_tokens": 2000,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 200,
                        },
                    },
                }
            )
        )
    # D4 block: 5 identical gpt-5.4-mini calls within 80s (cluster of 5 >= 3); day 2.
    base = datetime(2026, 6, 11, 14, 0, 0, tzinfo=UTC)
    for i in range(5):
        ts = base + timedelta(seconds=20 * i)
        lines.append(
            json.dumps(
                {
                    "request_id": f"wp-d4-{i:03d}",
                    "ts": ts.isoformat(),
                    "endpoint": "/v1/chat/completions",
                    "tag": "support-bot",
                    "request": {
                        "max_tokens": 512,
                        "messages": [{"role": "user", "content": D4_RETRY_TEXT}],
                    },
                    "response": {
                        "id": f"chatcmpl_wp_d4_{i:03d}",
                        "object": "chat.completion",
                        "created": int(ts.timestamp()),
                        "model": "gpt-5.4-mini",
                        "usage": {
                            "prompt_tokens": 500,
                            "completion_tokens": 200,
                            "prompt_tokens_details": {"cached_tokens": 0},
                        },
                    },
                }
            )
        )
    # --- waste_pack v2 blocks (D5 milestone) ---
    # D1 block: 25 short-completion opus-4-8 calls, unique prefixes, spaced 200s; day 1.
    base = datetime(2026, 6, 10, 13, 0, 0, tzinfo=UTC)
    for i in range(25):
        ts = base + timedelta(seconds=200 * i)
        lines.append(
            json.dumps(
                {
                    "request_id": f"wp-d1-{i:03d}",
                    "ts": ts.isoformat(),
                    "endpoint": "/v1/messages",
                    "tag": "extraction",
                    "request": {
                        "max_tokens": 200,
                        "system": f"D1-UNIQUE-{i} " * 60,
                        "messages": [{"role": "user", "content": f"extract {i}"}],
                    },
                    "response": {
                        "id": f"msg_wp_d1_{i:03d}",
                        "type": "message",
                        "model": "claude-opus-4-8",
                        "usage": {
                            "input_tokens": 1500,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 60,
                        },
                    },
                }
            )
        )
    # D3 blocks: lean route (40 x prompt 1000) vs bloated route (20 x prompt 6000),
    # same completion bin (350 tokens); day 2. Unique prefixes keep D2 silent.
    for tag, count, prompt, hour in (("rag-lean", 40, 1000, 9), ("rag-bloated", 20, 6000, 16)):
        base = datetime(2026, 6, 11, hour, 0, 0, tzinfo=UTC)
        for i in range(count):
            ts = base + timedelta(seconds=200 * i)
            lines.append(
                json.dumps(
                    {
                        "request_id": f"wp-d3-{tag}-{i:03d}",
                        "ts": ts.isoformat(),
                        "endpoint": "/v1/rag",
                        "tag": tag,
                        "request": {
                            "max_tokens": 1024,
                            "system": f"D3-{tag}-{i} " * 50,
                            "messages": [{"role": "user", "content": f"answer {i}"}],
                        },
                        "response": {
                            "id": f"msg_wp_d3_{tag}_{i:03d}",
                            "type": "message",
                            "model": "claude-haiku-4-5",
                            "usage": {
                                "input_tokens": prompt,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 0,
                                "output_tokens": 350,
                            },
                        },
                    }
                )
            )
    # D6 block: 12 small calls spaced 65s; even indices share one prefix (re-read
    # signature >= 5) but same-hash calls sit 130s apart (D4 stays silent); day 3.
    base = datetime(2026, 6, 12, 15, 0, 0, tzinfo=UTC)
    for i in range(12):
        ts = base + timedelta(seconds=65 * i)
        text = "D6-REREAD-CONTEXT " * 250 if i % 2 == 0 else f"D6-STEP-{i} " * 250
        lines.append(
            json.dumps(
                {
                    "request_id": f"wp-d6-{i:03d}",
                    "ts": ts.isoformat(),
                    "endpoint": "/v1/messages",
                    "tag": "agent-7",
                    "request": {
                        "max_tokens": 256,
                        "system": text,
                        "messages": [{"role": "user", "content": f"step {i}"}],
                    },
                    "response": {
                        "id": f"msg_wp_d6_{i:03d}",
                        "type": "message",
                        "model": "claude-haiku-4-5",
                        "usage": {
                            "input_tokens": 1200,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 80,
                        },
                    },
                }
            )
        )
    # D5 block (OpenAI shape): 12 calls declaring max_tokens 8192 vs ~120-token
    # completions; unique prefixes, spaced 200s; day 3.
    base = datetime(2026, 6, 12, 13, 0, 0, tzinfo=UTC)
    for i in range(12):
        ts = base + timedelta(seconds=200 * i)
        lines.append(
            json.dumps(
                {
                    "request_id": f"wp-d5-{i:03d}",
                    "ts": ts.isoformat(),
                    "endpoint": "/v1/chat/completions",
                    "tag": "generator",
                    "request": {
                        "max_tokens": 8192,
                        "messages": [{"role": "user", "content": f"D5-UNIQUE-{i} " * 60}],
                    },
                    "response": {
                        "id": f"chatcmpl_wp_d5_{i:03d}",
                        "object": "chat.completion",
                        "created": int(ts.timestamp()),
                        "model": "gpt-5.6-luna",
                        "usage": {
                            "prompt_tokens": 900,
                            "completion_tokens": 120,
                            "prompt_tokens_details": {"cached_tokens": 0},
                        },
                    },
                }
            )
        )
    # Benign filler (fires NOTHING): unique prefixes, prompt < 1024, spaced 200s; day 3.
    base = datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)
    for i in range(20):
        ts = base + timedelta(seconds=200 * i)
        lines.append(
            json.dumps(
                {
                    "request_id": f"wp-ok-{i:03d}",
                    "ts": ts.isoformat(),
                    "endpoint": "/v1/messages",
                    "tag": f"batch-{i % 4}",
                    "request": {
                        "max_tokens": 1024,
                        "system": f"UNIQUE-PREFIX-{i} " * 40,
                        "messages": [{"role": "user", "content": f"job {i}"}],
                    },
                    "response": {
                        "id": f"msg_wp_ok_{i:03d}",
                        "type": "message",
                        "model": "claude-haiku-4-5",
                        "usage": {
                            "input_tokens": 800,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 300,
                        },
                    },
                }
            )
        )
    # NOTE: waste_pack is mixed-provider in spirit but must stay single-format for
    # detect_format; both blocks use wrapper shape parseable by the ANTHROPIC parser?
    # No — D4 block is OpenAI-shaped. waste_pack is loaded per-block in tests via
    # two files. See main(): waste_pack_anthropic.jsonl + waste_pack_openai.jsonl.
    return lines


def _clean_optimal_lines() -> list[str]:
    """F6 false-positive guard: healthy traffic, ZERO findings expected from every
    detector (designed to stay silent through D5's detectors too: cached reads
    present, unique prefixes, no bursts, mid-size completions, sane max_tokens)."""
    lines: list[str] = []
    base = datetime(2026, 6, 10, 8, 0, 0, tzinfo=UTC)
    for i in range(60):
        ts = base + timedelta(hours=(i * 71) % 65, seconds=301 * i)
        lines.append(
            json.dumps(
                {
                    "request_id": f"co-{i:03d}",
                    "ts": ts.isoformat(),
                    "endpoint": "/v1/messages",
                    "tag": f"svc-{i % 3}",
                    "request": {
                        "max_tokens": 1024,
                        "system": f"WELL-CACHED-PREFIX-{i % 3} " * 100,
                        "messages": [{"role": "user", "content": f"task {i}"}],
                    },
                    "response": {
                        "id": f"msg_co_{i:03d}",
                        "type": "message",
                        "model": "claude-sonnet-5",
                        "usage": {
                            "input_tokens": 400,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 1500,
                            "output_tokens": 400,
                        },
                    },
                }
            )
        )
    return lines


def main(outdir: Path) -> None:
    rng = random.Random(SEED)
    outdir.mkdir(parents=True, exist_ok=True)

    (outdir / "openai_small.jsonl").write_text(
        "\n".join(json.dumps(_openai_line(rng, i)) for i in range(500)) + "\n"
    )
    (outdir / "anthropic_small.jsonl").write_text(
        "\n".join(json.dumps(_anthropic_line(rng, i)) for i in range(500)) + "\n"
    )
    (outdir / "mixed_dirty.jsonl").write_text("\n".join(_dirty_lines(rng, 500, 40)) + "\n")
    (outdir / "generic.csv").write_text("\n".join(_csv_lines(rng, 300)) + "\n")
    (outdir / "claude_code_session.jsonl").write_text(
        "\n".join(_claude_code_session(rng, 40)) + "\n"
    )
    waste = _waste_pack_lines()
    # split by provider shape: detect_format is per-file (see D2 milestone note)
    (outdir / "waste_pack_anthropic.jsonl").write_text(
        "\n".join(line for line in waste if '"type": "message"' in line) + "\n"
    )
    (outdir / "waste_pack_openai.jsonl").write_text(
        "\n".join(line for line in waste if '"chat.completion"' in line) + "\n"
    )
    (outdir / "clean_optimal.jsonl").write_text("\n".join(_clean_optimal_lines()) + "\n")
    print(f"fixtures written to {outdir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
